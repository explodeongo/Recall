"use client";

import { useQuery } from "@tanstack/react-query";
import { Layers, Loader2, Plus, RotateCw, Search, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { AddSources } from "@/components/AddSources";
import { StarButton } from "@/components/StarButton";
import { SourceIcon, StatusBadge, TagLink, sourceLabel, timeAgo } from "@/components/ItemBits";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { MARK_END, MARK_START, api, isBusy, passageHref, type Item } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function LibraryPage() {
  return (
    <Suspense fallback={<ListSkeleton />}>
      <Library />
    </Suspense>
  );
}

function Library() {
  const router = useRouter();
  const params = useSearchParams();
  const tag = params.get("tag") ?? undefined;
  const view = (["starred", "archived"].includes(params.get("view") ?? "") ? params.get("view") : "all") as "all" | "starred" | "archived";
  // The search box is live: it filters as you type, and the text is kept in the URL (?q=) so a
  // search survives a refresh and the back button.
  const [search, setSearch] = useState(params.get("q") ?? "");
  const q = useDebounced(search.trim(), 200);
  useEffect(() => {
    const next = new URLSearchParams(params.toString());
    if (q) next.set("q", q);
    else next.delete("q");
    if (next.toString() !== params.toString()) router.replace(next.size ? `/?${next}` : "/", { scroll: false });
  }, [q, params, router]);

  const items = useQuery({
    queryKey: ["items", tag ?? null, q, view],
    queryFn: () => api.items(tag, q || undefined, view),
    placeholderData: (previous) => previous, // keep the list while a new search loads
    // Keep polling while anything is still being read, so statuses update by themselves.
    refetchInterval: (query) => (query.state.data?.some((i) => isBusy(i.status)) ? 2000 : false),
  });
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags, refetchInterval: items.data?.some((i) => isBusy(i.status)) ? 4000 : false });

  const isEmptyLibrary = !tag && !q && view === "all" && items.data?.length === 0;
  const browsing = !tag && !q && view === "all";
  const count = items.data?.length ?? 0;

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-balance font-heading text-4xl font-medium">Library</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {items.data
              ? q
                ? `${count} ${count === 1 ? "result" : "results"} for “${q}”${tag ? ` in #${tag}` : ""}`
                : `${count} ${view === "starred" ? "starred " : view === "archived" ? "archived " : ""}${count === 1 ? "item" : "items"}${tag ? ` tagged #${tag}` : ""}`
              : " "}
          </p>
        </div>
        {!isEmptyLibrary && (
          <Link href="/add" className={buttonVariants({ size: "lg" })}>
            <Plus /> Add item
          </Link>
        )}
      </header>

      {!isEmptyLibrary && <SearchBar value={search} onChange={setSearch} searching={items.isFetching && !!q} />}

      {browsing && <Resurface />}

      {!isEmptyLibrary && !q && <ViewSwitch view={view} />}

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
        view !== "all" && !q ? (
          <p className="text-muted-foreground">
            {view === "starred" ? "Nothing starred yet. Star things you want to keep close." : "Nothing archived. Archive what you're done with; it stays searchable."}
          </p>
        ) : q ? (
          <div className="rounded-xl border border-dashed p-6 text-center">
            <p className="font-medium">No documents match “{q}”{tag ? ` in #${tag}` : ""}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Search looks for each word in titles, tags, summaries, your notes and the full text. Ask can also find things
              phrased differently.
            </p>
            <Link href={`/ask?q=${encodeURIComponent(q)}`} className={buttonVariants({ variant: "outline", className: "mt-4" })}>
              <Sparkles /> Ask Recall instead
            </Link>
          </div>
        ) : (
          <p className="text-muted-foreground">
            Nothing tagged #{tag}.{" "}
            <Link href="/" className="text-brand underline-offset-4 hover:underline">
              Show everything
            </Link>
          </p>
        )
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

/** Where a search matched: the passage with the words marked, linking to that spot. */
function MatchSnippet({ item }: { item: Item }) {
  const match = item.match!;
  const parts = match.snippet.split(MARK_START).flatMap((piece, i) => {
    if (i === 0) return [{ text: piece, hit: false }];
    const [hit, rest = ""] = piece.split(MARK_END);
    return [
      { text: hit, hit: true },
      { text: rest, hit: false },
    ];
  });
  const href =
    match.kind === "text" && match.chunk_id !== null
      ? passageHref({ item_id: item.id, chunk_id: match.chunk_id, start_char: match.start_char, end_char: match.end_char })
      : `/items/${item.id}`;
  return (
    <Link href={href} className="relative z-10 mt-2 line-clamp-3 rounded-lg bg-muted/50 px-3 py-2 text-sm text-muted-foreground transition-colors duration-150 hover:bg-muted">
      {match.kind === "related" ? (
        <span className="mr-1.5 inline-flex items-center gap-1 rounded-full bg-brand-soft px-1.5 text-[11px] font-medium text-brand">
          <Sparkles className="size-3" aria-hidden /> Related
        </span>
      ) : (
        match.page !== null && <span className="mr-1.5 text-xs tabular-nums">p. {match.page} ·</span>
      )}
      <span>
        {parts.map((p, i) =>
          p.hit ? (
            <mark key={i} className="rounded-sm bg-amber-200/70 px-0.5 text-foreground dark:bg-amber-400/25">
              {p.text}
            </mark>
          ) : (
            <span key={i}>{p.text}</span>
          ),
        )}
      </span>
    </Link>
  );
}

function ViewSwitch({ view }: { view: "all" | "starred" | "archived" }) {
  const views = [
    { id: "all", label: "All", href: "/" },
    { id: "starred", label: "Starred", href: "/?view=starred" },
    { id: "archived", label: "Archived", href: "/?view=archived" },
  ] as const;
  return (
    <nav aria-label="Show" className="flex gap-1 text-sm">
      {views.map((v) => (
        <Link
          key={v.id}
          href={v.href}
          aria-current={view === v.id ? "page" : undefined}
          className={cn(
            "rounded-md px-2.5 py-1 transition-colors duration-150",
            view === v.id ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
          )}
        >
          {v.label}
        </Link>
      ))}
    </nav>
  );
}

/** A few things saved a while ago and not opened since, and any flashcards due. */
function Resurface() {
  const data = useQuery({ queryKey: ["resurface"], queryFn: api.resurface, staleTime: 5 * 60_000 });
  if (!data.data || (data.data.items.length === 0 && data.data.cards_due === 0)) return null;
  const { items, cards_due } = data.data;
  if (items.length === 0) {
    return (
      <Link
        href="/review"
        className="flex items-center gap-2 rounded-xl border bg-card px-4 py-3 text-sm transition-colors duration-150 hover:border-brand/40"
      >
        <Layers className="size-4 text-brand" aria-hidden />
        <span>
          {cards_due} {cards_due === 1 ? "flashcard is" : "flashcards are"} ready to review
        </span>
        <span className="ml-auto text-brand">Review now</span>
      </Link>
    );
  }
  return (
    <section aria-labelledby="resurface-title" className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="resurface-title" className="font-heading text-xl font-medium">
          Worth another look
        </h2>
        {cards_due > 0 && (
          <Link href="/review" className="inline-flex items-center gap-1.5 text-sm text-brand underline-offset-4 hover:underline">
            <Layers className="size-4" aria-hidden /> {cards_due} {cards_due === 1 ? "card" : "cards"} to review
          </Link>
        )}
      </div>
      {items.length > 0 && (
        <ul className="grid gap-2 sm:grid-cols-3">
          {items.map((item) => (
            <li key={item.id}>
              <Link href={`/items/${item.id}`} className="flex h-full flex-col rounded-xl border bg-card p-4 transition-colors duration-150 hover:border-brand/40">
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  <SourceIcon type={item.source_type} className="size-3.5" />
                  Saved {timeAgo(item.created_at)}
                </span>
                <span className="mt-1.5 line-clamp-2 font-medium leading-snug">{item.title}</span>
                {item.summary && <span className="mt-1.5 line-clamp-3 text-sm text-muted-foreground">{item.summary}</span>}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
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
            <div className="relative z-10 flex shrink-0 items-center gap-1">
              {item.status !== "ready" && <StatusBadge status={item.status} />}
              <StarButton item={item} />
            </div>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {sourceLabel(item)} · {timeAgo(item.created_at)}
          </p>
          {item.match ? (
            <MatchSnippet item={item} />
          ) : (
            item.summary && <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{item.summary}</p>
          )}
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

/** Filters the documents as you type; "Ask" sends the same words to Ask instead. */
function SearchBar({ value, onChange, searching }: { value: string; onChange: (v: string) => void; searching: boolean }) {
  const router = useRouter();
  const input = useRef<HTMLInputElement>(null);

  // "/" focuses the search box, as in most apps with one.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(target.tagName) && !target.isContentEditable) {
        e.preventDefault();
        input.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div
      role="search"
      className="flex items-center gap-2 rounded-xl border bg-card py-1.5 pr-1.5 pl-4 shadow-xs transition focus-within:border-brand/60 focus-within:ring-3 focus-within:ring-brand/15"
    >
      {searching ? (
        <Loader2 className="size-4 animate-spin text-muted-foreground motion-reduce:animate-none" aria-hidden />
      ) : (
        <Search className="size-4 text-muted-foreground" aria-hidden />
      )}
      <input
        ref={input}
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") onChange("");
        }}
        placeholder="Search your documents…"
        aria-label="Search your documents"
        className="min-w-0 flex-1 bg-transparent py-1 text-[15px] outline-none placeholder:text-muted-foreground [&::-webkit-search-cancel-button]:hidden"
      />
      {value && (
        <Button type="button" size="icon-sm" variant="ghost" onClick={() => onChange("")} aria-label="Clear search">
          <X />
        </Button>
      )}
      <Button
        type="button"
        size="sm"
        variant="ghost"
        disabled={!value.trim()}
        onClick={() => router.push(`/ask?q=${encodeURIComponent(value.trim())}`)}
        className="text-brand"
      >
        <Sparkles /> Ask
      </Button>
      <kbd className="hidden rounded border bg-muted px-1.5 font-sans text-[11px] text-muted-foreground sm:inline" aria-hidden>
        /
      </kbd>
    </div>
  );
}

function useDebounced<T>(value: T, ms: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
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
