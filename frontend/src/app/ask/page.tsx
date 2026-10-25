"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowUp, ChevronDown, ExternalLink, FileQuestion, Loader2, Square } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { AnswerText } from "@/components/AnswerText";
import { SourceIcon } from "@/components/ItemBits";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, askStream, sourceHref, type AskDone, type Source } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Turn {
  id: number;
  question: string;
  sources: Source[] | null;
  text: string;
  done: AskDone | null;
  error: string | null;
}

export default function AskPage() {
  return (
    <Suspense>
      <Ask />
    </Suspense>
  );
}

function Ask() {
  const router = useRouter();
  const initial = useSearchParams().get("q");
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const abort = useRef<AbortController | null>(null);
  const started = useRef(false);
  const busy = turns[0] ? !turns[0].done && !turns[0].error : false;

  const update = (id: number, patch: (t: Turn) => Partial<Turn>) =>
    setTurns((all) => all.map((t) => (t.id === id ? { ...t, ...patch(t) } : t)));

  const ask = useCallback((q: string) => {
    const text = q.trim();
    if (!text) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    const id = Date.now();
    setTurns((all) => [{ id, question: text, sources: null, text: "", done: null, error: null }, ...all]);
    setQuestion("");
    askStream(
      text,
      {
        onSources: (sources) => update(id, () => ({ sources })),
        onDelta: (delta) => update(id, (t) => ({ text: t.text + delta })),
        onDone: (done) => update(id, () => ({ done, text: done.answer })),
        onError: (error) => update(id, () => ({ error })),
      },
      controller.signal,
    ).catch((err: Error) => {
      if (err.name !== "AbortError") update(id, () => ({ error: err.message }));
    });
  }, []);

  // A question handed over from the Library's search bar (?q=) is asked once on arrival.
  useEffect(() => {
    if (initial && !started.current) {
      started.current = true;
      ask(initial);
      router.replace("/ask");
    }
  }, [initial, ask, router]);

  function stop() {
    abort.current?.abort();
    if (!turns[0]) return;
    // Keep whatever had arrived; with nothing yet, show that it was stopped.
    update(turns[0].id, (t) =>
      t.text
        ? { done: { answer: t.text, not_found: false, cited: [], timings: { retrieval_ms: 0, llm_ms: 0, first_token_ms: null } } }
        : { error: "Stopped." },
    );
  }

  return (
    <div className="space-y-10">
      <header>
        <h1 className="text-balance font-heading text-4xl font-medium">Ask your library</h1>
        <p className="mt-2 text-muted-foreground">Answers come only from what you&apos;ve saved, with a numbered source for every claim.</p>
      </header>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(question);
        }}
        className="rounded-2xl border bg-card p-2 shadow-xs transition focus-within:border-brand/60 focus-within:ring-3 focus-within:ring-brand/15"
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
              ask(question);
            }
          }}
          placeholder="When is a hash index better than a B-tree?"
          className="block w-full resize-none bg-transparent px-3 py-2 text-[16px] outline-none placeholder:text-muted-foreground"
        />
        <div className="flex items-center justify-between px-2 pb-1">
          <span className="text-xs text-muted-foreground">Enter to ask · Shift+Enter for a new line</span>
          {/* One button whose icon cross-fades between Ask and Stop, so it never jumps. */}
          <Button
            type={busy ? "button" : "submit"}
            size="icon"
            onClick={busy ? stop : undefined}
            disabled={!busy && !question.trim()}
            aria-label={busy ? "Stop" : "Ask"}
            className={cn(
              "relative transition-[background-color,color,transform] duration-200",
              busy ? "bg-secondary text-secondary-foreground hover:bg-secondary/80" : "bg-brand text-brand-foreground hover:bg-brand/85",
            )}
          >
            <ArrowUp className={cn("icon-swap absolute", busy && "scale-50 opacity-0 blur-[2px]")} aria-hidden />
            <Square className={cn("icon-swap absolute size-3.5 fill-current", !busy && "scale-50 opacity-0 blur-[2px]")} aria-hidden />
          </Button>
        </div>
      </form>

      {turns.length === 0 && <Suggestions onPick={ask} />}

      <div className="space-y-12">
        {turns.map((turn, i) => (
          <TurnView key={turn.id} turn={turn} latest={i === 0} />
        ))}
      </div>
    </div>
  );
}

function Suggestions({ onPick }: { onPick: (q: string) => void }) {
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags });
  if (!tags.data) return null;
  if (tags.data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Your library is empty, so there&apos;s nothing to ask about yet.{" "}
        <Link href="/add" className="text-brand underline-offset-4 hover:underline">
          Add a PDF or a link
        </Link>{" "}
        first.
      </p>
    );
  }
  const picks = tags.data.slice(0, 4).map((t) => `What have I saved about ${t.name}?`);
  return (
    <div className="space-y-2">
      <h2 className="text-sm text-muted-foreground">Try one of these, or ask your own:</h2>
      <div className="flex flex-wrap gap-2">
        {picks.map((q) => (
          <button key={q} onClick={() => onPick(q)} className="rounded-full border bg-card px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-brand/50 hover:text-foreground">
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

function TurnView({ turn, latest }: { turn: Turn; latest: boolean }) {
  const streaming = !turn.done && !turn.error;
  const sources = turn.sources ?? [];
  const cited = turn.done?.cited ?? [];

  return (
    <section aria-live={latest ? "polite" : undefined} aria-busy={streaming} className={cn("animate-enter space-y-5", !latest && "opacity-80")}>
      <h2 className="text-balance font-heading text-2xl leading-snug">{turn.question}</h2>

      {turn.error && !turn.text ? (
        <p role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm">
          {turn.error === "Stopped." ? "Stopped." : `Something went wrong: ${turn.error}`}
        </p>
      ) : turn.done?.not_found ? (
        <NotFound />
      ) : turn.sources === null || (streaming && !turn.text) ? (
        <Thinking searching={turn.sources === null} />
      ) : (
        <AnswerText text={turn.text} sources={sources} streaming={streaming} />
      )}

      {turn.done && !turn.done.not_found && sources.length > 0 && <SourcesList sources={sources} cited={cited} />}
      {turn.done && !turn.done.not_found && turn.done.timings.llm_ms > 0 && (
        <p className="text-xs text-muted-foreground tabular-nums">
          Answered in {((turn.done.timings.retrieval_ms + turn.done.timings.llm_ms) / 1000).toFixed(1)} s · searched {sources.length} passages in{" "}
          {Math.round(turn.done.timings.retrieval_ms)} ms
        </p>
      )}
    </section>
  );
}

function Thinking({ searching }: { searching: boolean }) {
  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
        {searching ? "Searching your library…" : "Writing an answer from the best passages…"}
      </p>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
    </div>
  );
}

function NotFound() {
  return (
    <div className="flex gap-4 rounded-xl border bg-card p-5">
      <FileQuestion className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
      <div>
        <p className="font-medium">Not found in your library</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Nothing you&apos;ve saved answers this, so Recall won&apos;t guess. Try different words, or{" "}
          <Link href="/add" className="text-brand underline-offset-4 hover:underline">
            add a source
          </Link>{" "}
          that covers it.
        </p>
      </div>
    </div>
  );
}

function SourcesList({ sources, cited }: { sources: Source[]; cited: number[] }) {
  const [showAll, setShowAll] = useState(false);
  const citedSources = cited.map((n) => sources[n - 1]).filter(Boolean);
  const others = sources.filter((s) => !cited.includes(s.n));
  const shown = citedSources.length ? citedSources : sources;

  return (
    <div className="space-y-3">
      <h3 className="text-sm font-medium text-muted-foreground">{citedSources.length ? "Sources" : "Passages searched"}</h3>
      <ol className="grid gap-2">
        {shown.map((s, i) => (
          <SourceCard key={s.n} source={s} index={i} />
        ))}
      </ol>
      {citedSources.length > 0 && others.length > 0 && (
        <div>
          <button onClick={() => setShowAll((v) => !v)} className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors duration-150 hover:text-foreground" aria-expanded={showAll} aria-controls="other-passages">
            <ChevronDown className={cn("size-4 transition-transform duration-250 ease-(--ease-out)", showAll && "rotate-180")} />
            {showAll ? "Hide" : "Show"} {others.length} other {others.length === 1 ? "passage" : "passages"} Recall looked at
          </button>
          {/* Height animates through grid rows (0fr to 1fr), which needs no measuring. */}
          <div
            id="other-passages"
            inert={!showAll}
            className={cn(
              "grid transition-[grid-template-rows,opacity] duration-250 ease-(--ease-out) motion-reduce:transition-none",
              showAll ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
            )}
          >
            <div className="min-h-0 overflow-hidden">
              <ol className="grid gap-2 pt-2 opacity-80">
                {others.map((s) => (
                  <SourceCard key={s.n} source={s} animate={false} />
                ))}
              </ol>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SourceCard({ source, index = 0, animate = true }: { source: Source; index?: number; animate?: boolean }) {
  return (
    <li
      style={{ "--i": Math.min(index, 5) } as React.CSSProperties}
      className={cn("group relative rounded-xl border bg-card p-4 transition-colors duration-150 hover:border-brand/40", animate && "animate-enter")}
    >
      <div className="flex items-center gap-2 text-sm">
        <span className="grid size-5 shrink-0 place-items-center rounded-md bg-brand-soft text-xs font-semibold text-brand tabular-nums">{source.n}</span>
        <SourceIcon type={source.source_type} className="size-3.5" />
        <Link href={`/items/${source.item_id}?chunk=${source.chunk_id}`} className="min-w-0 truncate font-medium after:absolute after:inset-0">
          {source.title}
        </Link>
        {source.page && <span className="shrink-0 text-muted-foreground">p. {source.page}</span>}
        <a
          href={sourceHref(source, source.item_id, source.page)}
          target="_blank"
          rel="noreferrer"
          className="relative z-10 ml-auto shrink-0 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label={`Open ${source.title}${source.page ? ` at page ${source.page}` : ""}`}
        >
          <ExternalLink className="size-3.5" />
        </a>
      </div>
      <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">{source.text}</p>
    </li>
  );
}
