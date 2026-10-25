"use client";

import { ChevronDown, ExternalLink, FileQuestion, Loader2 } from "lucide-react";
import Link from "next/link";
import { useId, useState } from "react";
import { SourceIcon } from "@/components/ItemBits";
import { Skeleton } from "@/components/ui/skeleton";
import { passageHref, sourceHref, sourceName, type Source } from "@/lib/api";
import { cn } from "@/lib/utils";

export function Thinking({ searching }: { searching: boolean }) {
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

export function NotFound() {
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

export function SourceCard({ source, index = 0, animate = true }: { source: Source; index?: number; animate?: boolean }) {
  return (
    <li
      style={{ "--i": Math.min(index, 5) } as React.CSSProperties}
      className={cn("group relative rounded-xl border bg-card p-4 transition-colors duration-150 hover:border-brand/40", animate && "animate-enter")}
    >
      <div className="flex items-center gap-2 text-sm">
        <span className="grid size-5 shrink-0 place-items-center rounded-md bg-brand-soft text-xs font-semibold text-brand tabular-nums">{source.n}</span>
        <SourceIcon type={source.source_type} className="size-3.5" />
        <Link href={passageHref(source)} className="min-w-0 truncate font-medium after:absolute after:inset-0">
          {sourceName(source)}
        </Link>
        {source.page && <span className="shrink-0 text-muted-foreground">p. {source.page}</span>}
        <a
          href={sourceHref(source, source.item_id, source.page)}
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
