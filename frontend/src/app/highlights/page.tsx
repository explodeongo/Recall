"use client";

import { useQuery } from "@tanstack/react-query";
import { Highlighter } from "lucide-react";
import Link from "next/link";
import { timeAgo } from "@/components/ItemBits";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type HighlightWithItem } from "@/lib/api";

/** Every highlight across the library, grouped by document, newest documents first. */
export default function HighlightsPage() {
  const highlights = useQuery({ queryKey: ["all-highlights"], queryFn: api.allHighlights });

  const groups = new Map<number, { title: string; items: HighlightWithItem[] }>();
  for (const h of highlights.data ?? []) {
    const group = groups.get(h.item_id) ?? { title: h.item_title, items: [] };
    group.items.push(h);
    groups.set(h.item_id, group);
  }

  return (
    <div className="mx-auto max-w-3xl space-y-10">
      <header>
        <h1 className="font-heading text-4xl font-medium">Highlights</h1>
        <p className="mt-2 text-muted-foreground">Everything you&apos;ve marked while reading. Click one to open it in place.</p>
      </header>

      {highlights.isPending ? (
        <div className="space-y-3" aria-busy="true" aria-label="Loading highlights">
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : highlights.isError ? (
        <p role="alert" className="text-muted-foreground">
          {highlights.error.message}
        </p>
      ) : groups.size === 0 ? (
        <div className="rounded-2xl border border-dashed p-8 text-center">
          <Highlighter className="mx-auto size-6 text-muted-foreground" aria-hidden />
          <p className="mt-3 font-medium">No highlights yet</p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
            Open any document, switch to Read, and select text to highlight it or add a note.
          </p>
        </div>
      ) : (
        [...groups.entries()].map(([itemId, group]) => (
          <section key={itemId} aria-labelledby={`h-${itemId}`} className="space-y-3">
            <h2 id={`h-${itemId}`} className="font-heading text-xl font-medium">
              <Link href={`/items/${itemId}?view=read`} className="underline-offset-4 hover:underline">
                {group.title}
              </Link>
            </h2>
            <ul className="space-y-2">
              {group.items.map((h) => (
                <li key={h.id}>
                  <Link
                    href={`/items/${h.item_id}?from=${h.start_char}&to=${h.end_char}`}
                    className="block rounded-xl border bg-card shadow-xs p-4 transition-colors duration-150 hover:border-amber-400/60"
                  >
                    <span className="font-heading text-[17px] leading-relaxed">
                      <span className="rounded-sm bg-amber-200/60 px-0.5 [box-decoration-break:clone] dark:bg-amber-400/20">{h.quote}</span>
                    </span>
                    {h.note && <span className="mt-2 block text-sm">{h.note}</span>}
                    <span className="mt-2 block text-xs text-muted-foreground">{timeAgo(h.created_at)}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
