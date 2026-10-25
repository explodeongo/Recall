"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Plus, RotateCw, Search } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AddSources } from "@/components/AddSources";
import { SourceIcon, StatusBadge, TagLink, sourceLabel, timeAgo } from "@/components/ItemBits";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, isBusy, type Item } from "@/lib/api";

export default function LibraryPage() {
  return (
    <Suspense fallback={<ListSkeleton />}>
      <Library />
    </Suspense>
  );
}

function Library() {
  const tag = useSearchParams().get("tag") ?? undefined;
  const items = useQuery({
    queryKey: ["items", tag ?? null],
    queryFn: () => api.items(tag),
    // Keep polling while anything is still being read, so statuses update by themselves.
    refetchInterval: (query) => (query.state.data?.some((i) => isBusy(i.status)) ? 2000 : false),
  });
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags, refetchInterval: items.data?.some((i) => isBusy(i.status)) ? 4000 : false });

  const isEmptyLibrary = !tag && items.data?.length === 0;

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-balance font-heading text-4xl font-medium">Library</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {items.data ? `${items.data.length} ${items.data.length === 1 ? "item" : "items"}${tag ? ` tagged #${tag}` : ""}` : " "}
          </p>
        </div>
        {!isEmptyLibrary && (
          <Link href="/add" className={buttonVariants({ size: "lg" })}>
            <Plus /> Add item
          </Link>
        )}
      </header>

      {!isEmptyLibrary && <AskBar />}

      {tags.data && tags.data.length > 0 && (
        <nav aria-label="Filter by tag" className="flex flex-wrap gap-1.5">
          {tags.data.map((t) => (
            <TagLink key={t.id} tag={t} count={t.item_count} active={tag === t.name} />
          ))}
        </nav>
      )}

      {items.isPending ? (
        <ListSkeleton />
      ) : items.isError ? (
        <div role="alert" className="flex items-center justify-between gap-4 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm">
          <span>{items.error.message}</span>
          <Button variant="outline" size="sm" onClick={() => items.refetch()}>
            <RotateCw /> Retry
          </Button>
        </div>
      ) : isEmptyLibrary ? (
        <EmptyLibrary />
      ) : items.data.length === 0 ? (
        <p className="text-muted-foreground">
          Nothing tagged #{tag}.{" "}
          <Link href="/" className="text-brand underline-offset-4 hover:underline">
            Show everything
          </Link>
        </p>
      ) : (
        <ul className="divide-y rounded-xl border bg-card">
          {items.data.map((item) => (
            <ItemRow key={item.id} item={item} activeTag={tag} />
          ))}
        </ul>
      )}
    </div>
  );
}

function ItemRow({ item, activeTag }: { item: Item; activeTag?: string }) {
  return (
    <li className="group relative px-4 py-4 transition-colors first:rounded-t-xl last:rounded-b-xl hover:bg-muted/40 sm:px-5">
      <div className="flex items-start gap-3">
        <SourceIcon type={item.source_type} className="mt-1" />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <Link href={`/items/${item.id}`} className="font-medium leading-snug after:absolute after:inset-0 focus-visible:outline-none">
              <span className="line-clamp-2 break-words">{item.title}</span>
            </Link>
            {item.status !== "ready" && <StatusBadge status={item.status} className="shrink-0" />}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {sourceLabel(item)} · {timeAgo(item.created_at)}
          </p>
          {item.summary && <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{item.summary}</p>}
          {item.status === "failed" && item.error && <p className="mt-2 line-clamp-2 text-sm text-destructive">{item.error}</p>}
          {item.tags.length > 0 && (
            // Above the row's full-size link, so the tags stay clickable.
            <div className="relative z-10 mt-2.5 flex flex-wrap gap-1">
              {item.tags.map((t) => (
                <TagLink key={t.id} tag={t} active={activeTag === t.name} />
              ))}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

function AskBar() {
  const router = useRouter();
  const [q, setQ] = useState("");
  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) router.push(`/ask?q=${encodeURIComponent(q.trim())}`);
      }}
      className="group flex items-center gap-2 rounded-xl border bg-card px-4 py-2.5 shadow-xs transition focus-within:border-brand/60 focus-within:ring-3 focus-within:ring-brand/15"
    >
      <Search className="size-4 text-muted-foreground" aria-hidden />
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Ask your library a question…"
        aria-label="Ask your library a question"
        className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground"
      />
      <Button type="submit" size="sm" variant="ghost" disabled={!q.trim()} aria-label="Ask">
        <ArrowRight />
      </Button>
    </form>
  );
}

function EmptyLibrary() {
  return (
    <section aria-labelledby="empty-title" className="mx-auto max-w-2xl space-y-6 pt-4">
      <div>
        <h2 id="empty-title" className="font-heading text-2xl font-medium">
          Start with one thing you&apos;ve read
        </h2>
        <p className="mt-2 text-muted-foreground">
          Save a PDF or an article link. Recall reads it in a few seconds, writes a summary and tags it. Then you can{" "}
          <Link href="/ask" className="text-brand underline-offset-4 hover:underline">
            ask it questions
          </Link>{" "}
          and get answers that point to the exact passage.
        </p>
      </div>
      <AddSources />
    </section>
  );
}

function ListSkeleton() {
  return (
    <div className="divide-y rounded-xl border" aria-busy="true" aria-label="Loading">
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="flex gap-3 p-5">
          <Skeleton className="size-4" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-3 w-1/4" />
            <Skeleton className="h-3 w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
