"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BookmarkPlus, Check, ChevronDown, Copy, ExternalLink, FileQuestion, Globe, Loader2 } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";
import { SourceIcon } from "@/components/ItemBits";
import { ListenButton } from "@/components/Listen";
import { toast } from "sonner";
import { Skeleton } from "@/components/ui/skeleton";
import { api, imageSrc, passageHref, siteOf, sourceHref, sourceName, type Source } from "@/lib/api";
import { cn } from "@/lib/utils";

export function Thinking({ searching, status }: { searching: boolean; status?: string | null }) {
  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 text-sm text-muted-foreground" aria-live="polite">
        {status?.toLowerCase().includes("web") ? (
          <Globe className="size-4 animate-pulse text-brand motion-reduce:animate-none" aria-hidden />
        ) : (
          <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
        )}
        {status ?? (searching ? "Searching your library…" : "Writing an answer from the best passages…")}
      </p>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
    </div>
  );
}

export function NotFound({ searchedWeb = false }: { searchedWeb?: boolean }) {
  return (
    <div className="flex gap-4 rounded-xl border bg-card shadow-xs p-5">
      <FileQuestion className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
      <div>
        <p className="font-medium">{searchedWeb ? "Not found in your library or on the web" : "Not found in your library"}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {searchedWeb
            ? "Recall looked in your library and on the web and found nothing that answers this, so it won't guess. "
            : "Nothing you've saved answers this, so Recall won't guess. "}
          Try different words, or{" "}
          <Link href="/add" className="text-brand underline-offset-4 hover:underline">
            add a source
          </Link>{" "}
          that covers it.
        </p>
      </div>
    </div>
  );
}

/** Figures from the documents an answer cites, placed beside the cited passages. Each opens
 * the passage, figure included. */
export function AnswerFigures({ sources, cited }: { sources: Source[]; cited: number[] }) {
  const seen = new Set<number>();
  const figures: { id: number; alt: string | null; width: number; height: number; source: Source; n: number }[] = [];
  for (const n of cited) {
    const source = sources[n - 1];
    for (const image of source?.images ?? []) {
      if (seen.has(image.id)) continue;
      seen.add(image.id);
      figures.push({ ...image, source, n });
    }
  }
  if (!figures.length) return null;
  return (
    <ul className="flex gap-3 overflow-x-auto pb-1" aria-label="Figures from the sources">
      {figures.slice(0, 4).map((f, i) => (
        <li key={f.id} className={cn("shrink-0 animate-enter", figures.length === 1 ? "w-full max-w-md" : "w-56")} style={{ "--i": i } as React.CSSProperties}>
          <Link href={passageHref(f.source)} className="group block">
            {/* eslint-disable-next-line @next/next/no-img-element -- served by the API */}
            <img
              src={imageSrc(`/images/${f.id}`)}
              alt={f.alt ?? `Figure from ${f.source.title}`}
              width={f.width}
              height={f.height}
              loading="lazy"
              className={cn(
                "w-full rounded-xl border bg-muted object-contain shadow-xs transition-[border-color] duration-150 group-hover:border-brand/50",
                figures.length === 1 ? "h-64" : "h-36",
              )}
            />
            <span className="mt-1.5 flex items-start gap-1.5 text-xs text-muted-foreground">
              <span className="mt-px inline-grid h-4 min-w-4 place-items-center rounded bg-brand-soft px-1 text-[10px] font-semibold text-brand tabular-nums">{f.n}</span>
              <span className="line-clamp-2">{f.alt || f.source.title}</span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function SourcesList({ sources, cited }: { sources: Source[]; cited: number[] }) {
  const [showAll, setShowAll] = useState(false);
  const panelId = useId();
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
          <button onClick={() => setShowAll((v) => !v)} className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors duration-150 hover:text-foreground" aria-expanded={showAll} aria-controls={panelId}>
            <ChevronDown className={cn("size-4 transition-transform duration-250 ease-(--ease-out)", showAll && "rotate-180")} />
            {showAll ? "Hide" : "Show"} {others.length} other {others.length === 1 ? "passage" : "passages"} Recall looked at
          </button>
          {/* Height animates through grid rows (0fr to 1fr), which needs no measuring. */}
          <div
            id={panelId}
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

/** Shown above an answer that came (at least partly) from the web, so it's never mistaken for
 *  something from the user's own library. */
export function FromTheWeb({ partly }: { partly: boolean }) {
  return (
    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <Globe className="size-3.5 text-brand" aria-hidden />
      {partly ? "Partly from your library, partly from the web" : "Not in your library. Answered from the web"}
    </p>
  );
}

export function SourceCard({ source, index = 0, animate = true }: { source: Source; index?: number; animate?: boolean }) {
  if (source.kind === "web") return <WebSourceCard source={source} index={index} animate={animate} />;
  return (
    <li
      style={{ "--i": Math.min(index, 5) } as React.CSSProperties}
      className={cn("group relative rounded-xl border bg-card shadow-xs p-4 transition-colors duration-150 hover:border-brand/40", animate && "animate-enter")}
    >
      <div className="flex items-center gap-2 text-sm">
        <span className="grid size-5 shrink-0 place-items-center rounded-md bg-brand-soft text-xs font-semibold text-brand tabular-nums">{source.n}</span>
        <SourceIcon type={source.source_type} className="size-3.5" />
        <Link href={passageHref(source)} className="min-w-0 truncate font-medium after:absolute after:inset-0">
          {sourceName(source)}
        </Link>
        {source.page && <span className="shrink-0 text-muted-foreground">p. {source.page}</span>}
        <a
          href={sourceHref(source, source.item_id ?? 0, source.page, source.text) ?? passageHref(source)}
          target="_blank"
          rel="noreferrer"
          className="relative z-10 ml-auto shrink-0 rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label={`Open ${sourceName(source)}${source.page ? ` at page ${source.page}` : ""}`}
        >
          <ExternalLink className="size-3.5" />
        </a>
      </div>
      <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">{source.text}</p>
    </li>
  );
}

function WebSourceCard({ source, index, animate }: { source: Source; index: number; animate: boolean }) {
  return (
    <li
      style={{ "--i": Math.min(index, 5) } as React.CSSProperties}
      className={cn("group relative rounded-xl border border-dashed bg-card p-4 transition-colors duration-150 hover:border-brand/40", animate && "animate-enter")}
    >
      <div className="flex items-center gap-2 text-sm">
        <span className="grid size-5 shrink-0 place-items-center rounded-md border border-brand/30 text-xs font-semibold text-brand tabular-nums">{source.n}</span>
        <Globe className="size-3.5 shrink-0 text-muted-foreground" aria-label="Web page" />
        <a href={source.source} target="_blank" rel="noreferrer" className="min-w-0 truncate font-medium after:absolute after:inset-0">
          {source.title}
        </a>
        <span className="ml-auto shrink-0 text-xs text-muted-foreground">{siteOf(source.source)}</span>
        <ExternalLink className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
      </div>
      <p className="mt-2 line-clamp-3 text-sm text-muted-foreground">{source.text}</p>
    </li>
  );
}

/** Under a finished answer: read it aloud, keep it as a note, copy it. */
export function AnswerActions({
  chatId,
  message,
  question,
  sources,
}: {
  chatId: number | null;
  message: { id: number; content: string; cited: number[] | null; saved_item_id?: number | null };
  question: string;
  sources: Source[];
}) {
  const queryClient = useQueryClient();
  const [savedId, setSavedId] = useState(message.saved_item_id ?? null);
  const [copied, setCopied] = useState(false);
  const save = useMutation({
    mutationFn: () => api.saveAnswer(chatId!, message.id),
    onSuccess: (item) => {
      setSavedId(item.id);
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["chat", chatId] });
      toast.success("Saved to your library as a note. Recall is reading it now.");
    },
    onError: (err) => toast.error(err.message),
  });
  const cited = (message.cited ?? []).filter((n) => sources[n - 1]);
  const plain =
    message.content.trim() +
    (cited.length ? "\n\nSources:\n" + cited.map((n) => `[${n}] ${sources[n - 1].title}`).join("\n") : "");

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <ListenButton id={`answer-${message.id}`} title={question} text={message.content} />
      {savedId ? (
        <Link
          href={`/items/${savedId}`}
          className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 px-2.5 py-1 text-xs text-emerald-700 transition-colors duration-150 hover:bg-emerald-500/10 dark:text-emerald-400"
        >
          <Check className="size-3.5" aria-hidden /> Saved as a note
        </Link>
      ) : (
        <button
          type="button"
          onClick={() => save.mutate()}
          disabled={save.isPending || chatId === null}
          className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs text-muted-foreground transition-[color,border-color,transform] duration-150 hover:border-brand/50 hover:text-foreground active:scale-[0.97] disabled:opacity-50"
        >
          {save.isPending ? <Loader2 className="size-3.5 animate-spin motion-reduce:animate-none" aria-hidden /> : <BookmarkPlus className="size-3.5" aria-hidden />}
          Save as note
        </button>
      )}
      <button
        type="button"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(plain);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          } catch {
            toast.error("Couldn't copy. Select the text and copy it instead.");
          }
        }}
        className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs text-muted-foreground transition-[color,border-color,transform] duration-150 hover:border-brand/50 hover:text-foreground active:scale-[0.97]"
      >
        {copied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}
