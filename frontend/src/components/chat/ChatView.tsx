"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, AtSign, FileText, Globe, Hash, History, MessageSquareText, RotateCw, Search, Square } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { AnswerText } from "@/components/AnswerText";
import { AnswerActions, AnswerFigures, FromTheWeb, NotFound, SourcesList, SuggestedQuestions, Thinking } from "@/components/chat/AnswerParts";
import { ChatList } from "@/components/chat/ChatList";
import { MentionMenu, PinnedChips, SourceSwitch, mentionAt, useAnswerSource, useMentions, type Mention, type Pinned } from "@/components/chat/ContextPicker";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, sendChatMessage, type AnswerSource, type Chat, type ChatMessage, type MessageContext, type MessageDone, type Source } from "@/lib/api";
import { cn } from "@/lib/utils";

/** The answer being streamed in right now, before it's saved into the chat. */
interface Pending {
  question: string;
  context: MessageContext;
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
  // Where answers come from: library, library + web, or web; remembered per browser.
  const [source, setSource] = useAnswerSource();
  // "@" context: answers only from these items and tags, kept for follow-ups until removed.
  const [pinned, setPinned] = useState<Pinned>({ items: [], tags: [] });
  const abort = useRef<AbortController | null>(null);
  const started = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);

  const chat = useQuery({ queryKey: ["chat", chatId], queryFn: () => api.chat(chatId!), enabled: chatId !== null });
  const itemId = chat.data?.item_id ?? (Number(params.get("item")) || null);
  const item = useQuery({ queryKey: ["item", itemId], queryFn: () => api.item(itemId!), enabled: itemId !== null });
  const busy = pending !== null && pending.error === null;

  // Reopening a chat picks up where it was: the last question's "@" context stays pinned.
  const restored = useRef<number | null>(null);
  useEffect(() => {
    if (!chat.data || restored.current === chat.data.id) return;
    restored.current = chat.data.id;
    const last = [...chat.data.messages].reverse().find((m) => m.role === "user");
    if (last?.context) setPinned({ items: last.context.items, tags: last.context.tags });
  }, [chat.data]);

  // `from` overrides where this one answer may come from, e.g. the web after the library had
  // nothing; the chosen default stays as it is.
  const ask = useCallback(
    async (raw: string, from?: AnswerSource) => {
      const question = raw.trim();
      if (!question || busy) return;
      const context: MessageContext = { ...pinned, source: from ?? source };
      setPending({ question, context, query: null, sources: null, text: "", error: null, status: null });

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
        context,
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
    [busy, chatId, itemId, queryClient, setPending, pinned, source],
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
            <div className="mt-3 animate-enter rounded-xl border bg-card shadow-xs p-3">
              <ChatList activeId={chatId} onNavigate={() => setHistoryOpen(false)} />
            </div>
          )}
        </div>

        {/* The window's full height below the nav (the page's bottom padding is taken back),
            so the question box sits at the bottom like any chat, with the conversation above. */}
        <div className="mx-auto -mb-24 flex min-h-[calc(100dvh-5.5rem)] max-w-3xl flex-col">
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
            <div className="flex-1 space-y-10 pb-4">
              {turnsOf(messages).map(([question, answer], i, all) => (
                <Exchange
                  key={question.id}
                  // Follow-ups only under the latest answer, and not while another is coming.
                  onAsk={i === all.length - 1 && !pending ? ask : undefined}
                  onSearchWeb={i === all.length - 1 && !pending ? (q) => ask(q, "web") : undefined}
                  chatId={chatId}
                  question={question.content}
                  context={question.context ?? null}
                  searchQuery={question.search_query}
                  answer={answer}
                />
              ))}
              {pending && <PendingExchange pending={pending} onRetry={ask} />}
            </div>
          )}
          <Composer
            busy={busy}
            onAsk={ask}
            onStop={stop}
            source={source}
            onSourceChange={setSource}
            pinned={pinned}
            onPinnedChange={setPinned}
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
  const items = useQuery({ queryKey: ["mention-items"], queryFn: () => api.items(), enabled: !scoped, staleTime: 60_000 });
  // Two from the biggest topics, two about things saved lately.
  const suggestions = [
    ...(tags.data ?? [])
      .filter((t) => t.item_count > 1)
      .slice(0, 2)
      .map((t) => ({ q: `What have I saved about ${t.name}?`, from: `#${t.name}`, icon: Hash })),
    ...(items.data ?? [])
      .filter((i) => i.status === "ready" && i.source_type !== "note")
      .slice(0, 2)
      .map((i) => ({ q: `What are the main ideas in “${i.title}”?`, from: "Saved recently", icon: FileText })),
  ];
  const libraryEmpty = !scoped && tags.data?.length === 0 && items.data?.length === 0;

  return (
    <header className="flex flex-1 flex-col items-center justify-center py-10 text-center">
      <span className="grid size-11 place-items-center rounded-xl bg-brand-soft text-brand" aria-hidden>
        <MessageSquareText className="size-5" />
      </span>
      <h1 className="mt-4 text-balance font-heading text-4xl font-medium">{scoped ? "Ask about this document" : "Ask your library"}</h1>
      <p className="mt-2 max-w-md text-pretty text-muted-foreground">
        {scoped
          ? "Answers come only from this document, each claim with the passage it's from."
          : "Answers come from what you've saved, each claim with a numbered source. Ask follow-ups, or type @ to ask about one item or tag."}
      </p>
      {libraryEmpty && (
        <p className="mt-6 text-sm text-muted-foreground">
          Your library is empty, so there&apos;s nothing to ask about yet.{" "}
          <Link href="/add" className="text-brand underline-offset-4 hover:underline">
            Add a PDF or a link
          </Link>{" "}
          first.
        </p>
      )}
      {suggestions.length > 0 && (
        <ul className="mt-8 grid w-full gap-2 text-left sm:grid-cols-2" aria-label="Questions to try">
          {suggestions.map(({ q, from, icon: Icon }, i) => (
            // Two on a phone, so the question box never covers one.
            <li key={q} className={cn("animate-enter", i >= 2 && "hidden sm:block")} style={{ "--i": i } as React.CSSProperties}>
              <button
                onClick={() => onPick(q)}
                className="group flex h-full w-full flex-col gap-1.5 rounded-xl border bg-card p-3.5 text-left shadow-xs transition-[border-color,background-color,transform] duration-150 ease-(--ease-out) hover:border-brand/40 hover:bg-brand-soft/30 active:scale-[0.99]"
              >
                <span className="line-clamp-2 text-sm leading-snug">{q}</span>
                <span className="mt-auto flex items-center gap-1 text-xs text-muted-foreground">
                  <Icon className="size-3" aria-hidden /> {from}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </header>
  );
}

function Exchange({
  chatId,
  question,
  context,
  searchQuery,
  answer,
  onAsk,
  onSearchWeb,
}: {
  onAsk?: (q: string) => void;
  /** Ask the same question of the web, offered when the library had nothing. */
  onSearchWeb?: (q: string) => void;
  chatId: number | null;
  question: string;
  context: MessageContext | null;
  searchQuery: string | null;
  answer: ChatMessage;
}) {
  const sources = answer.sources ?? [];
  const cited = (answer.cited ?? []).map((n) => sources[n - 1]).filter(Boolean);
  const fromWeb = cited.some((s) => s.kind === "web");
  return (
    <section className="space-y-4">
      <Question text={question} context={context} searchQuery={searchQuery} />
      {answer.not_found ? (
        <NotFound searchedWeb={answer.content.includes("web")} onSearchWeb={onSearchWeb && (() => onSearchWeb(question))} />
      ) : (
        <>
          {fromWeb && context?.source !== "web" && <FromTheWeb partly={cited.some((s) => s.kind !== "web")} />}
          <AnswerText text={answer.content} sources={sources} />
          <AnswerFigures sources={sources} cited={answer.cited ?? []} />
          <AnswerActions chatId={chatId} message={answer} question={question} sources={sources} />
          {sources.length > 0 && <SourcesList sources={sources} cited={answer.cited ?? []} />}
          {onAsk && <SuggestedQuestions questions={answer.suggestions ?? []} onAsk={onAsk} />}
        </>
      )}
    </section>
  );
}

function PendingExchange({ pending, onRetry }: { pending: Pending; onRetry: (q: string) => void }) {
  const sources = pending.sources ?? [];
  return (
    <section aria-live="polite" aria-busy={pending.error === null} className="animate-enter space-y-4">
      <Question text={pending.question} context={pending.context} searchQuery={pending.query} />
      {pending.error && !pending.text ? (
        <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm">
          <p className="min-w-0 flex-1">
            {pending.error === "Stopped." ? "Stopped. This question wasn't saved." : `${pending.error.replace(/\.$/, "")}. Your question wasn't saved.`}
          </p>
          <Button size="sm" variant="outline" onClick={() => onRetry(pending.question)}>
            <RotateCw /> Try again
          </Button>
        </div>
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

function Question({ text, context, searchQuery }: { text: string; context: MessageContext | null; searchQuery: string | null }) {
  const rewritten = searchQuery && searchQuery.trim().toLowerCase() !== text.trim().toLowerCase();
  return (
    <div className="flex flex-col items-end gap-1.5">
      {context && (context.items.length > 0 || context.tags.length > 0) && (
        <div className="flex max-w-[85%] justify-end">
          <PinnedChips pinned={context} />
        </div>
      )}
      <p className="max-w-[85%] rounded-2xl rounded-br-md bg-muted px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap">{text}</p>
      {context?.source === "web" && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Globe className="size-3 shrink-0" aria-hidden /> Asked the web only
        </p>
      )}
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
  source,
  onSourceChange,
  pinned,
  onPinnedChange,
}: {
  busy: boolean;
  onAsk: (q: string) => void;
  onStop: () => void;
  placeholder?: string;
  source: AnswerSource;
  onSourceChange: (s: AnswerSource) => void;
  pinned: Pinned;
  onPinnedChange: (p: Pinned) => void;
}) {
  const [question, setQuestion] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  const form = useRef<HTMLFormElement>(null);
  // The "@" being typed, if any, and the highlighted option in its menu.
  const [mention, setMention] = useState<{ start: number; query: string } | null>(null);
  const [active, setActive] = useState(0);
  const options = useMentions(mention?.query ?? "", pinned, mention !== null);

  const send = () => {
    if (!question.trim() || busy) return;
    onAsk(question);
    setQuestion("");
    setMention(null);
  };

  const track = (text: string, caret: number) => {
    const found = mentionAt(text, caret);
    setMention(found);
    if (found?.query !== mention?.query) setActive(0);
  };

  const pick = (m: Mention) => {
    if (m.kind === "tag") onPinnedChange({ ...pinned, tags: [...pinned.tags, m.name] });
    else onPinnedChange({ ...pinned, items: [...pinned.items, { id: m.id, title: m.title }] });
    // Put the name where "@query" was, so the question still reads as a sentence
    // ("what does Attention Is All You Need say…"); the chip does the limiting.
    if (mention) {
      const caret = box.current?.selectionStart ?? question.length;
      const name = (m.kind === "tag" ? m.name : m.title) + " ";
      const next = question.slice(0, mention.start) + name + question.slice(caret).replace(/^ /, "");
      const at = mention.start + name.length;
      setQuestion(next);
      requestAnimationFrame(() => box.current?.setSelectionRange(at, at));
    }
    setMention(null);
  };

  const unpin = (m: Mention) =>
    onPinnedChange(
      m.kind === "tag" ? { ...pinned, tags: pinned.tags.filter((t) => t !== m.name) } : { ...pinned, items: pinned.items.filter((i) => i.id !== m.id) },
    );

  const openMenu = () => {
    const el = box.current!;
    const caret = el.selectionStart ?? question.length;
    el.focus();
    // Already typing an @ (or the menu's open): just show the menu for it, don't add another.
    if (mention) return;
    if (question[caret - 1] === "@") {
      setMention({ start: caret - 1, query: "" });
      setActive(0);
      return;
    }
    const spacer = caret > 0 && !/\s/.test(question[caret - 1]) ? " " : "";
    const next = question.slice(0, caret) + spacer + "@" + question.slice(caret);
    setQuestion(next);
    el.focus();
    const at = caret + spacer.length + 1;
    requestAnimationFrame(() => el.setSelectionRange(at, at));
    setMention({ start: at - 1, query: "" });
    setActive(0);
  };

  const pinnedAny = pinned.items.length > 0 || pinned.tags.length > 0;

  return (
    // Pinned to the bottom of the window, over a fade so the conversation slides under it.
    <div className="sticky bottom-0 -mx-2 bg-gradient-to-t from-background from-70% to-transparent px-2 pt-6 pb-4">
      <form
        ref={form}
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="relative rounded-2xl border bg-card p-2 shadow-sm transition focus-within:border-brand/60 focus-within:ring-3 focus-within:ring-brand/15"
      >
        {mention && <MentionMenu options={options} active={active} onPick={pick} query={mention.query} anchor={form} />}
        {pinnedAny && (
          <div className="px-2 pt-1">
            <PinnedChips pinned={pinned} onRemove={unpin} />
          </div>
        )}
        <label htmlFor="question" className="sr-only">
          Your question
        </label>
        <textarea
          id="question"
          ref={box}
          autoFocus
          rows={2}
          value={question}
          maxLength={1000}
          role="combobox"
          aria-expanded={mention !== null}
          aria-controls={mention ? "mention-menu" : undefined}
          aria-activedescendant={mention && options.length ? `mention-${active}` : undefined}
          aria-autocomplete="list"
          onChange={(e) => {
            setQuestion(e.target.value);
            track(e.target.value, e.target.selectionStart);
          }}
          onSelect={(e) => track(e.currentTarget.value, e.currentTarget.selectionStart)}
          onBlur={() => setMention(null)}
          onKeyDown={(e) => {
            if (mention) {
              if (e.key === "ArrowDown" || e.key === "ArrowUp") {
                e.preventDefault();
                const n = options.length || 1;
                setActive((a) => (a + (e.key === "ArrowDown" ? 1 : n - 1)) % n);
                return;
              }
              if ((e.key === "Enter" || e.key === "Tab") && options[active]) {
                e.preventDefault();
                pick(options[active]);
                return;
              }
              if (e.key === "Escape") {
                e.preventDefault();
                setMention(null);
                return;
              }
            }
            if (e.key === "Backspace" && !question && pinnedAny) {
              // An empty box: backspace takes off the last pin, as in most chip inputs.
              const lastItem = pinned.items.at(-1);
              if (lastItem) unpin({ kind: "item", ...lastItem });
              else unpin({ kind: "tag", name: pinned.tags.at(-1)! });
              return;
            }
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send();
            }
          }}
          placeholder={placeholder ?? "Ask anything. Type @ to limit it to an item or tag."}
          className="block w-full resize-none bg-transparent px-3 py-2 text-[16px] outline-none placeholder:text-muted-foreground"
        />
        <div className="flex items-center gap-2 px-2 pb-1">
          <SourceSwitch value={source} onChange={onSourceChange} />
          <button
            type="button"
            onClick={openMenu}
            disabled={source === "web"}
            title={source === "web" ? "Web-only answers don't use your library" : "Limit the answer to items or tags"}
            className="flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs text-muted-foreground transition-[color,border-color,transform] duration-150 hover:text-foreground active:scale-[0.97] disabled:opacity-40"
          >
            <AtSign className="size-3.5" aria-hidden />
            <span className="hidden sm:inline">Context</span>
          </button>
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
      {source === "web" && pinnedAny && <p className="mt-1.5 px-2 text-xs text-muted-foreground">Pinned items are ignored while answering from the web only.</p>}
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
      {
        id: userId,
        role: "user",
        content: pending.question,
        context: pending.context,
        sources: null,
        cited: null,
        not_found: false,
        search_query: pending.query,
        created_at: now,
      },
      {
        id: replyId,
        role: "assistant",
        content: done.answer,
        sources: pending.sources ?? [],
        cited: done.cited,
        not_found: done.not_found,
        suggestions: done.suggestions,
        search_query: null,
        created_at: now,
      },
    ],
  };
}
