"use client";

import { useQuery } from "@tanstack/react-query";
import { Network } from "lucide-react";
import Link from "next/link";
import { SourceIcon, tagStyle } from "@/components/ItemBits";
import { api, passageHref, type Item } from "@/lib/api";

/** Other saved items on a related topic, each with the passage in it that connects them. */
export function Connections({ item }: { item: Item }) {
  const found = useQuery({ queryKey: ["connections", item.id], queryFn: () => api.connections(item.id), staleTime: 60_000 });
  if (!found.data?.length) return null;
  const colors = new Map(found.data.flatMap((c) => c.item.tags.map((t) => [t.name, t.color] as const)));

  return (
    <section aria-labelledby="connections-title" className="max-w-[68ch] space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="connections-title" className="font-heading text-2xl font-medium">
          Connected in your library
        </h2>
        <Link href={`/graph?focus=${item.id}`} className="inline-flex items-center gap-1.5 text-sm text-brand underline-offset-4 hover:underline">
          <Network className="size-4" aria-hidden /> See the graph
        </Link>
      </div>
      <ul className="space-y-2">
        {found.data.map((c, i) => (
          <li key={c.item.id} className="animate-enter" style={{ "--i": i } as React.CSSProperties}>
            <div className="group relative rounded-xl border bg-card shadow-xs p-4 transition-colors duration-150 hover:border-brand/40">
              <div className="flex items-start gap-2.5">
                <SourceIcon type={c.item.source_type} className="mt-0.5" />
                <div className="min-w-0 flex-1">
                  <Link href={`/items/${c.item.id}`} className="font-medium leading-snug after:absolute after:inset-0 focus-visible:outline-none">
                    {c.item.title}
                  </Link>
                  <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    <span>{c.similarity >= 0.7 ? "Closely related" : "Related topic"}</span>
                    {c.shared_tags.map((name) => (
                      <span key={name} style={tagStyle(colors.get(name) ?? "#8d8d86")} className="tag-chip rounded-full border px-1.5 text-[11px]">
                        #{name}
                      </span>
                    ))}
                  </p>
                </div>
              </div>
              {c.passage && (
                <Link
                  href={passageHref({ item_id: c.item.id, chunk_id: c.passage.chunk_id, start_char: c.passage.start_char, end_char: c.passage.end_char, kind: "text" })}
                  className="relative z-10 mt-3 line-clamp-3 rounded-lg bg-muted/50 px-3 py-2 text-sm text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-foreground"
                >
                  {c.passage.page !== null && <span className="mr-1.5 text-xs tabular-nums">p. {c.passage.page} ·</span>}
                  {c.passage.text}
                </Link>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
