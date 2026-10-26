"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, FileText, Globe, History, Search, Square } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AnswerText } from "@/components/AnswerText";
import { FromTheWeb, NotFound, SourcesList, Thinking } from "@/components/chat/AnswerParts";
import { ChatList } from "@/components/chat/ChatList";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, sendChatMessage, type Chat, type ChatMessage, type MessageDone, type Source } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The answer being streamed in right now, before it's saved into the chat. */
interface Pending {
  question: string;
  query: string | null;
  sources: Source[] | null;
  text: string;
  error: string | null;
  status: string | null;
}

export function ChatView({ chatId: initialId }: { chatId: number | null }) {
  const queryClient = useQueryClient();
  const params = useSearchParams();
  const [chatId, setChatId] = useState(initialId);
  const [pending, setPendingState] = useState<Pending | null>(null);
  // Mirrors `pending` so callbacks can read the latest value without side effects in updaters.
  const pendingRef = useRef<Pending | null>(null);
  const setPending = useCallback((next: Pending | null | ((p: Pending | null) => Pending | null)) => {
    pendingRef.current = typeof next === "function" ? next(pendingRef.current) : next;
    setPendingState(pendingRef.current);
  }, []);
  const [historyOpen, setHistoryOpen] = useState(false);
  // Whether to search the web for what the library doesn't cover; remembered per browser.
  const [web, setWebState] = useState(true);
  useEffect(() => {
    try {
      if (localStorage.getItem("recall-web") === "off") setWebState(false);
    } catch {}
  }, []);
  const setWeb = (on: boolean) => {
    setWebState(on);
    try {
      localStorage.setItem("recall-web", on ? "on" : "off");
    } catch {}
  };
  const abort = useRef<AbortController | null>(null);
  const started = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);

  const chat = useQuery({ queryKey: ["chat", chatId], queryFn: () => api.chat(chatId!), enabled: chatId !== null });
  const itemId = chat.data?.item_id ?? (Number(params.get("item")) || null);
  const item = useQuery({ queryKey: ["item", itemId], queryFn: () => api.item(itemId!), enabled: itemId !== null });
  const busy = pending !== null && pending.error === null;

  const ask = useCallback(
    async (raw: string) => {
      const question = raw.trim();
      if (!question || busy) return;
      setPending({ question, query: null, sources: null, text: "", error: null, status: null });

      let id = chatId;
      if (id === null) {
        try {
          const created = await api.createChat(itemId ?? undefined);
          id = created.id;
          queryClient.setQueryData(["chat", id], created);
          setChatId(id);
          // Give the new chat its own address without remounting the page mid-answer.
          window.history.replaceState(null, "", `/ask/${id}`);
        } catch (err) {
          setPending((p) => p && { ...p, error: (err as Error).message });
          return;
        }
      }

      const controller = new AbortController();
      abort.current = controller;
      const chatKey = ["chat", id];
      await sendChatMessage(
        id,
        question,
        web,
        {
          onQuery: (query) => setPending((p) => p && { ...p, query }),
          onStatus: (status) => setPending((p) => p && { ...p, status }),
          onSources: (sources) => setPending((p) => p && { ...p, sources }),
          onDelta: (delta) => setPending((p) => p && { ...p, text: p.text + delta }),
          onDone: (done) => {
            const finished = pendingRef.current;
            if (finished) queryClient.setQueryData<Chat>(chatKey, (c) => c && appendTurn(c, finished, done));
            setPending(null);
            queryClient.invalidateQueries({ queryKey: ["chats"] });
          },
          onError: (error) => setPending((p) => p && { ...p, error }),
        },
        controller.signal,
      );
    },
    [busy, chatId, itemId, queryClient, setPending, web],
  );

  // A question handed over from the Library's search bar (?q=) is asked once on arrival.
  useEffect(() => {
    const q = params.get("q");
    if (q && !started.current && chatId === null) {
      started.current = true;
      ask(q);
    }
  }, [params, ask, chatId]);

  // Follow the conversation as it grows, unless the reader has scrolled up to look at something.
  const messageCount = chat.data?.messages.length ?? 0;
  useEffect(() => {
    const el = bottom.current;
    if (!el) return;
    const nearBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 240;
    if (nearBottom || pending?.text === "") el.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [messageCount, pending?.text, pending?.sources]);

  function stop() {
    abort.current?.abort();
    setPending((p) => p && { ...p, error: "Stopped." });
  }

  const messages = chat.data?.messages ?? [];
  const empty = messages.length === 0 && pending === null;

  return (
    <div className="mx-auto grid max-w-6xl gap-8 md:grid-cols-[15rem_minmax(0,1fr)]">
      <aside className="hidden md:block">
        <div className="sticky top-22">
          <ChatList activeId={chatId} />
        </div>
      </aside>

      <div className="min-w-0">
        <div className="mb-6 md:hidden">
          <Button variant="outline" size="sm" onClick={() => setHistoryOpen((v) => !v)} aria-expanded={historyOpen}>
            <History /> Chats
          </Button>
          {historyOpen && (
            <div className="mt-3 animate-enter rounded-xl border bg-card p-3">
              <ChatList activeId={chatId} onNavigate={() => setHistoryOpen(false)} />
            </div>
          )}
        </div>

        <div className="mx-auto max-w-3xl">
          {itemId !== null && (
            <p className="mb-6 flex items-center gap-2 rounded-lg border bg-brand-soft/40 px-3 py-2 text-sm">
              <FileText className="size-4 shrink-0 text-brand" aria-hidden />
              <span className="min-w-0 truncate">
                Only searching{" "}
                {item.data ? (
                  <Link href={`/items/${item.data.id}`} className="font-medium underline-offset-4 hover:underline">
                    {item.data.title}
                  </Link>
                ) : (
                  "one document"
                )}
              </span>
            </p>
          )}

          {chatId !== null && chat.isPending ? (
            <div className="space-y-4" aria-busy="true" aria-label="Loading chat">
              <Skeleton className="ml-auto h-10 w-2/3 rounded-2xl" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
            </div>
          ) : chat.isError ? (
            <p role="alert" className="text-muted-foreground">
              {chat.error.message === "Chat not found" ? "This chat was deleted." : chat.error.message}{" "}
              <Link href="/ask" className="text-brand underline-offset-4 hover:underline">
                Start a new chat
              </Link>
            </p>
          ) : empty ? (
            <Welcome scoped={itemId !== null} onPick={ask} />
          ) : (
            <div className="space-y-10 pb-4">
              {turnsOf(messages).map(([question, answer]) => (
                <Exchange key={question.id} question={question.content} searchQuery={question.search_query} answer={answer} />
              ))}
              {pending && <PendingExchange pending={pending} />}
            </div>
          )}
          <Composer
            busy={busy}
            onAsk={ask}
            onStop={stop}
            web={web}
            onWebChange={setWeb}
            placeholder={!empty ? "Ask a follow-up…" : itemId !== null ? "Ask anything about this document…" : undefined}
          />
          {/* Below the pinned question box, so scrolling here shows the newest text above it. */}
          <div ref={bottom} />
        </div>
      </div>
    </div>
  );
}

function Welcome({ scoped, onPick }: { scoped: boolean; onPick: (q: string) => void }) {
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags, enabled: !scoped });
  return (
    <header className="space-y-6 pt-2 pb-8">
      <div>
        <h1 className="text-balance font-heading text-4xl font-medium">{scoped ? "Ask about this document" : "Ask your library"}</h1>
        <p className="mt-2 text-muted-foreground">
          Answers come only from what you&apos;ve saved, with a numbered source for every claim. Ask follow-ups; Recall keeps the
          conversation, and saves it so you can come back to it.
        </p>
      </div>
      {!scoped && tags.data && tags.data.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Your library is empty, so there&apos;s nothing to ask about yet.{" "}
          <Link href="/add" className="text-brand underline-offset-4 hover:underline">
            Add a PDF or a link
          </Link>{" "}
          first.
        </p>
      )}
      {!scoped && tags.data && tags.data.length > 0 && (
        <div className="space-y-2">
          <h2 className="text-sm text-muted-foreground">Try one of these, or ask your own:</h2>
          <div className="flex flex-wrap gap-2">
            {tags.data.filter((t) => t.item_count > 0).slice(0, 4).map((t) => {
              const q = `What have I saved about ${t.name}?`;
              return (
                <button
                  key={t.id}
                  onClick={() => onPick(q)}
                  className="rounded-full border bg-card px-3 py-1.5 text-sm text-muted-foreground transition-[color,border-color,transform] duration-150 hover:border-brand/50 hover:text-foreground active:scale-[0.97]"
                >
                  {q}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </header>
  );
}

function Exchange({ question, searchQuery, answer }: { question: string; searchQuery: string | null; answer: ChatMessage }) {
  const sources = answer.sources ?? [];
  const cited = (answer.cited ?? []).map((n) => sources[n - 1]).filter(Boolean);
  const fromWeb = cited.some((s) => s.kind === "web");
  return (
    <section className="space-y-4">
      <Question text={question} searchQuery={searchQuery} />
      {answer.not_found ? (
        <NotFound searchedWeb={answer.content.includes("web")} />
      ) : (
        <>
          {fromWeb && <FromTheWeb partly={cited.some((s) => s.kind !== "web")} />}
          <AnswerText text={answer.content} sources={sources} />
          {sources.length > 0 && <SourcesList sources={sources} cited={answer.cited ?? []} />}
        </>
      )}
    </section>
  );
}

function PendingExchange({ pending }: { pending: Pending }) {
  const sources = pending.sources ?? [];
  return (
    <section aria-live="polite" aria-busy={pending.error === null} className="animate-enter space-y-4">
      <Question text={pending.question} searchQuery={pending.query} />
      {pending.error && !pending.text ? (
        <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm">
          {pending.error === "Stopped." ? "Stopped. This question wasn't saved." : `Something went wrong: ${pending.error}. This question wasn't saved; try asking again.`}
        </p>
      ) : pending.sources === null || !pending.text ? (
        <Thinking searching={pending.sources === null} status={pending.status} />
      ) : (
        <>
          <AnswerText text={pending.text} sources={sources} streaming={pending.error === null} />
          {/* The library part has arrived and the web is being searched for the rest. */}
          {pending.status && pending.error === null && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
              <Globe className="size-4 animate-pulse text-brand motion-reduce:animate-none" aria-hidden /> {pending.status}
            </p>
          )}
        </>
      )}
    </section>
  );
}

function Question({ text, searchQuery }: { text: string; searchQuery: string | null }) {
  const rewritten = searchQuery && searchQuery.trim().toLowerCase() !== text.trim().toLowerCase();
  return (
    <div className="flex flex-col items-end gap-1.5">
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-muted px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap">{text}</p>
      {rewritten && (
        <p className="flex max-w-[85%] items-center gap-1.5 text-xs text-muted-foreground">
          <Search className="size-3 shrink-0" aria-hidden />
          <span className="truncate">Searched for: {searchQuery}</span>
        </p>
      )}
    </div>
  );
}

function Composer({
  busy,
  onAsk,
  onStop,
  placeholder,
  web,
  onWebChange,
}: {
  busy: boolean;
  onAsk: (q: string) => void;
  onStop: () => void;
  placeholder?: string;
  web: boolean;
  onWebChange: (on: boolean) => void;
}) {
  const [question, setQuestion] = useState("");
  const send = () => {
    if (!question.trim() || busy) return;
    onAsk(question);
    setQuestion("");
  };
  return (
    // Pinned to the bottom of the window, over a fade so the conversation slides under it.
    <div className="sticky bottom-0 -mx-2 bg-gradient-to-t from-background from-70% to-transparent px-2 pt-6 pb-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="rounded-2xl border bg-card p-2 shadow-sm transition focus-within:border-brand/60 focus-within:ring-3 focus-within:ring-brand/15"
      >
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <textarea
          id="question"
          autoFocus
          rows={2}
          value={question}
          maxLength={1000}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder={placeholder ?? "When is a hash index better than a B-tree?"}
          className="block w-full resize-none bg-transparent px-3 py-2 text-[16px] outline-none placeholder:text-muted-foreground"
        />
        <div className="flex items-center justify-between px-2 pb-1">
          <button
            type="button"
            onClick={() => onWebChange(!web)}
            aria-pressed={web}
            title={web ? "Searching the web for what your library doesn't cover" : "Answers only from your library"}
            className={cn(
              "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-[color,background-color,border-color,transform] duration-150 active:scale-[0.97]",
              web ? "border-brand/40 bg-brand-soft text-brand" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Globe className="size-3.5" aria-hidden />
            {web ? "Web on" : "Library only"}
          </button>
          <span className="hidden text-xs text-muted-foreground md:inline">Enter to ask · Shift+Enter for a new line</span>
          {/* One button whose icon cross-fades between Ask and Stop, so it never jumps. */}
          <Button
            type={busy ? "button" : "submit"}
            size="icon"
            onClick={busy ? onStop : undefined}
            disabled={!busy && !question.trim()}
            aria-label={busy ? "Stop" : "Ask"}
            className={cn(
              "relative ml-auto transition-[background-color,color,transform] duration-200",
              busy ? "bg-secondary text-secondary-foreground hover:bg-secondary/80" : "bg-brand text-brand-foreground hover:bg-brand/85",
            )}
          >
            <ArrowUp className={cn("icon-swap absolute", busy && "scale-50 opacity-0 blur-[2px]")} aria-hidden />
            <Square className={cn("icon-swap absolute size-3.5 fill-current", !busy && "scale-50 opacity-0 blur-[2px]")} aria-hidden />
          </Button>
        </div>
      </form>
    </div>
  );
}

function turnsOf(messages: ChatMessage[]): [ChatMessage, ChatMessage][] {
  const turns: [ChatMessage, ChatMessage][] = [];
  for (let i = 0; i + 1 < messages.length; i += 2) {
    if (messages[i].role === "user" && messages[i + 1].role === "assistant") turns.push([messages[i], messages[i + 1]]);
  }
  return turns;
}

/** Add a finished exchange to the cached chat, so it appears without refetching. */
function appendTurn(chat: Chat, pending: Pending, done: MessageDone): Chat {
  const now = new Date().toISOString();
  const [userId, replyId] = done.message_ids;
  return {
    ...chat,
    title: done.title,
    messages: [
      ...chat.messages,
      { id: userId, role: "user", content: pending.question, sources: null, cited: null, not_found: false, search_query: pending.query, created_at: now },
      {
        id: replyId,
        role: "assistant",
        content: done.answer,
        sources: pending.sources ?? [],
        cited: done.cited,
        not_found: done.not_found,
        search_query: null,
        created_at: now,
      },
    ],
  };
}
