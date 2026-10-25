"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlignLeft, Archive, ArrowLeft, BookOpen, ExternalLink, Layers, Loader2, MessageSquareText, MoreHorizontal, Pencil, Plus, Quote, RotateCw, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useId, useMemo, useRef, useState } from "react";
import { HighlightReader } from "@/components/HighlightReader";
import { type Mark, joinPages } from "@/components/Reader";
import { toast } from "sonner";
import { SourceIcon, StatusBadge, sourceLabel, timeAgo } from "@/components/ItemBits";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { StarButton } from "@/components/StarButton";
import { Button, buttonVariants } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, isBusy, sourceHref, type Item, type ItemDetails } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function ItemPage() {
  return (
    <Suspense fallback={<ItemSkeleton />}>
      <ItemView />
    </Suspense>
  );
}

function ItemView() {
  const id = Number(useParams<{ id: string }>().id);
  const params = useSearchParams();
  const chunkId = Number(params.get("chunk")) || null;
  const from = params.get("from") === null ? null : Number(params.get("from"));
  const to = params.get("to") === null ? null : Number(params.get("to"));
  const range = from !== null && to !== null && Number.isFinite(from) && to > from ? { from, to } : null;
  // A citation opens the document itself, scrolled to the passage; otherwise the summary.
  const [view, setView] = useState<"summary" | "read">(range || chunkId || params.get("view") === "read" ? "read" : "summary");
  const item = useQuery({
    queryKey: ["item", id],
    queryFn: () => api.item(id),
    refetchInterval: (query) => (query.state.data && isBusy(query.state.data.status) ? 1500 : false),
  });
  // Only an item seen being read on this visit gets the reveal; opening a finished one is instant.
  const sawProcessing = useRef(false);
  const [renaming, setRenaming] = useState(false);
  // Record the visit once, so "Worth another look" doesn't suggest what was just read.
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current || !item.data || item.data.status !== "ready") return;
    opened.current = true;
    api.markOpened(id).catch(() => {});
  }, [id, item.data]);

  if (item.isPending) return <ItemSkeleton />;
  if (item.isError) {
    return (
      <div className="mx-auto max-w-4xl space-y-4">
        <BackLink />
        <p role="alert" className="text-muted-foreground">
          {item.error.message === "Item not found" ? "This item doesn't exist, or it was deleted." : item.error.message}
        </p>
      </div>
    );
  }
  const data = item.data;
  if (isBusy(data.status)) sawProcessing.current = true;

  return (
    <article className="mx-auto max-w-4xl space-y-8">
      <BackLink />
      <header className="space-y-3">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-muted-foreground">
          <SourceIcon type={data.source_type} />
          <span>{sourceLabel(data)}</span>
          <span aria-hidden>·</span>
          <span>Saved {timeAgo(data.created_at)}</span>
          {data.status !== "ready" && <StatusBadge status={data.status} />}
        </div>
        {renaming ? (
          <RenameTitle item={data} onDone={() => setRenaming(false)} />
        ) : (
          <h1 className="text-balance font-heading text-3xl leading-tight font-medium break-words sm:text-4xl">
            {data.archived && <span className="mr-2 align-middle font-sans text-xs font-medium tracking-normal text-muted-foreground">Archived</span>}
            {data.title}
          </h1>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          {data.status === "ready" && (
            <Link href={`/ask?item=${data.id}`} className={cn(buttonVariants(), "bg-brand text-brand-foreground hover:bg-brand/85")}>
              <MessageSquareText /> Ask about this document
            </Link>
          )}
          {data.status === "ready" && <QuizButton item={data} />}
          {sourceHref(data, data.id) && (
            <a href={sourceHref(data, data.id)!} target="_blank" rel="noreferrer" className={buttonVariants({ variant: "outline" })}>
              <ExternalLink />
              {{ pdf: "Open PDF", file: "Download file", youtube: "Watch on YouTube", url: "Open original", note: "" }[data.source_type]}
            </a>
          )}
          <StarButton item={data} className="size-8" />
          <ItemMenu item={data} onRename={() => setRenaming(true)} />
        </div>
        {data.status !== "queued" && data.status !== "processing" && <TagEditor item={data} />}
      </header>

      {isBusy(data.status) && <Processing status={data.status} />}
      {data.status === "failed" && <Failed item={data} />}

      {data.status === "ready" && (
        <Tabs value={view} onValueChange={(v) => setView(v as "summary" | "read")} className="gap-8">
          <TabsList>
            <TabsTrigger value="summary">
              <AlignLeft /> Summary
            </TabsTrigger>
            <TabsTrigger value="read">
              <BookOpen /> Read
            </TabsTrigger>
          </TabsList>
          <TabsContent value="summary">
            {data.summary && (
              <div className={cn("space-y-10", sawProcessing.current && "animate-develop")}>
                <p className="max-w-[65ch] font-heading text-xl leading-relaxed text-pretty">{data.summary}</p>
                <ItemNote item={data} />
                <Flashcards item={data} />
                {data.details ? <Details details={data.details} /> : <NoDetails item={data} />}
              </div>
            )}
          </TabsContent>
          <TabsContent value="read">
            <DocumentText item={data} chunkId={range ? null : chunkId} range={range} />
          </TabsContent>
        </Tabs>
      )}
    </article>
  );
}

/** "Quiz me": makes flashcards the first time, then opens a quiz on this item's cards. */
function QuizButton({ item }: { item: Item }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const cards = useQuery({ queryKey: ["cards", item.id], queryFn: () => api.itemCards(item.id) });
  const make = useMutation({
    mutationFn: () => api.generateCards(item.id),
    onSuccess: (made) => {
      queryClient.setQueryData(["cards", item.id], made);
      queryClient.invalidateQueries({ queryKey: ["review-stats"] });
      queryClient.removeQueries({ queryKey: ["review-queue"] });
      router.push(`/review?item=${item.id}`);
    },
    onError: (err) => toast.error(err.message),
  });
  const has = (cards.data?.length ?? 0) > 0;
  return (
    <Button
      variant="outline"
      disabled={make.isPending || cards.isPending}
      onClick={() => {
        if (has) {
          queryClient.removeQueries({ queryKey: ["review-queue"] });
          router.push(`/review?item=${item.id}`);
        } else make.mutate();
      }}
    >
      {make.isPending ? <Loader2 className="animate-spin" /> : <Layers />}
      {make.isPending ? "Writing questions…" : "Quiz me"}
    </Button>
  );
}

/** This item's flashcards: see them, delete ones that aren't useful, or make more. */
function Flashcards({ item }: { item: Item }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const cards = useQuery({ queryKey: ["cards", item.id], queryFn: () => api.itemCards(item.id) });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["cards", item.id] });
    queryClient.invalidateQueries({ queryKey: ["review-stats"] });
    queryClient.removeQueries({ queryKey: ["review-queue"] });
  };
  const more = useMutation({ mutationFn: () => api.generateCards(item.id), onSuccess: refresh, onError: (err) => toast.error(err.message) });
  const remove = useMutation({ mutationFn: (id: number) => api.deleteCard(id), onSuccess: refresh, onError: (err) => toast.error(err.message) });
  if (!cards.data?.length) return null;

  return (
    <section aria-labelledby="cards-title" className="max-w-[68ch] space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <h2 id="cards-title" className="font-heading text-2xl font-medium">
          Flashcards <span className="text-base text-muted-foreground tabular-nums">{cards.data.length}</span>
        </h2>
        <div className="flex gap-1">
          <Button size="sm" variant="ghost" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? "Hide" : "Show"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => more.mutate()} disabled={more.isPending}>
            {more.isPending ? <Loader2 className="animate-spin" /> : <Plus />} Make more
          </Button>
        </div>
      </div>
      {open && (
        <ul className="animate-enter divide-y rounded-xl border bg-card">
          {cards.data.map((card) => (
            <li key={card.id} className="group flex gap-3 p-4 text-sm">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{card.question}</p>
                <p className="mt-1 text-muted-foreground">{card.answer}</p>
              </div>
              <Button
                size="icon-sm"
                variant="ghost"
                className="text-muted-foreground opacity-0 group-hover:opacity-100 focus-visible:opacity-100 pointer-coarse:opacity-100"
                onClick={() => remove.mutate(card.id)}
                aria-label="Delete this card"
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** The reader's own note: saved as they type, and searchable by Ask once saved. */
function ItemNote({ item }: { item: Item }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState(item.note ?? "");
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function change(value: string) {
    setNote(value);
    setState("saving");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      try {
        const updated = await api.setNote(item.id, value);
        queryClient.setQueryData(["item", item.id], updated);
        setState("saved");
      } catch {
        setState("error");
      }
    }, 800);
  }

  return (
    <section id="notes" aria-labelledby="notes-title" className="max-w-[68ch] scroll-mt-24 space-y-2">
      <div className="flex items-baseline justify-between">
        <h2 id="notes-title" className="font-heading text-2xl font-medium">
          Your notes
        </h2>
        <span className="text-xs text-muted-foreground" aria-live="polite">
          {state === "saving" ? "Saving…" : state === "saved" ? "Saved. Ask can use these now." : state === "error" ? "Couldn't save. Keep typing to retry." : ""}
        </span>
      </div>
      <textarea
        value={note}
        onChange={(e) => change(e.target.value)}
        rows={note ? Math.min(12, note.split("\n").length + 2) : 3}
        maxLength={50000}
        placeholder="What you think about this, how it connects to other things you've read…"
        aria-labelledby="notes-title"
        className="block w-full resize-y rounded-xl border bg-card px-4 py-3 text-[15px] leading-relaxed outline-none transition focus:border-brand/60 focus:ring-3 focus:ring-brand/15"
      />
    </section>
  );
}

/** The page-long summary: overview, key points, then the document's parts in order. */
function Details({ details }: { details: ItemDetails }) {
  const paragraphs = details.overview.split(/\n\s*\n/).filter(Boolean);
  return (
    <div className="max-w-[68ch] space-y-10">
      {paragraphs.length > 0 && (
        <section aria-labelledby="overview" className="space-y-3">
          <h2 id="overview" className="font-heading text-2xl font-medium">
            Overview
          </h2>
          {paragraphs.map((p, i) => (
            <p key={i} className="text-[16px] leading-7 text-pretty">
              {p}
            </p>
          ))}
        </section>
      )}
      {details.key_points.length > 0 && (
        <section aria-labelledby="key-points" className="space-y-3">
          <h2 id="key-points" className="font-heading text-2xl font-medium">
            Key points
          </h2>
          <ul className="space-y-2.5">
            {details.key_points.map((point, i) => (
              <li key={i} className="flex gap-3 text-[16px] leading-7">
                <span className="mt-[0.7rem] size-1.5 shrink-0 rounded-full bg-brand" aria-hidden />
                <span className="text-pretty">{point}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {details.sections.length > 0 && (
        <section aria-labelledby="sections" className="space-y-5">
          <h2 id="sections" className="font-heading text-2xl font-medium">
            Section by section
          </h2>
          <ol className="space-y-5">
            {details.sections.map((section, i) => (
              <li key={i} className="grid gap-1 sm:grid-cols-[2rem_minmax(0,1fr)]">
                <span className="hidden pt-0.5 text-sm text-muted-foreground tabular-nums sm:block" aria-hidden>
                  {i + 1}
                </span>
                <div>
                  <h3 className="font-medium">{section.heading}</h3>
                  <p className="mt-1 text-[15px] leading-7 text-muted-foreground text-pretty">{section.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

/** Items saved before full summaries existed can get one by being read again. */
function NoDetails({
  item,
  reason = "This item was saved before Recall wrote full summaries.",
  action = "Write a full summary",
}: {
  item: Item;
  reason?: string;
  action?: string;
}) {
  const queryClient = useQueryClient();
  const redo = useMutation({
    mutationFn: () => api.reprocess(item.id),
    onSuccess: (updated) => {
      queryClient.setQueryData(["item", item.id], updated);
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
    onError: (err) => toast.error(err.message),
  });
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-dashed p-4 text-sm text-muted-foreground">
      <span className="flex-1">{reason}</span>
      <Button variant="outline" size="sm" onClick={() => redo.mutate()} disabled={redo.isPending}>
        <RotateCw className={redo.isPending ? "animate-spin" : ""} /> {action}
      </Button>
    </div>
  );
}

/** The item's tags: click a tag to filter the library, × to remove it, or type to add one. */
function TagEditor({ item }: { item: Item }) {
  const queryClient = useQueryClient();
  const allTags = useQuery({ queryKey: ["tags"], queryFn: api.tags });
  const [draft, setDraft] = useState("");
  const listId = useId();
  const save = useMutation({
    mutationFn: (names: string[]) => api.setTags(item.id, names),
    onMutate: (names) => {
      const previous = queryClient.getQueryData<Item>(["item", item.id]);
      queryClient.setQueryData<Item>(["item", item.id], (old) => old && { ...old, tags: names.map((name, id) => ({ id: -id - 1, name })) });
      return { previous };
    },
    onError: (err, _names, context) => {
      queryClient.setQueryData(["item", item.id], context?.previous);
      toast.error(err.message);
    },
    onSuccess: (updated) => queryClient.setQueryData(["item", item.id], updated),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
    },
  });
  const names = item.tags.map((t) => t.name);

  function add() {
    const name = draft.trim().toLowerCase().replace(/\s+/g, " ");
    setDraft("");
    if (!name || names.includes(name)) return;
    if (names.length >= 12) {
      toast.error("An item can have up to 12 tags.");
      return;
    }
    save.mutate([...names, name]);
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 pt-2" aria-label="Tags">
      {item.tags.map((t) => (
        <span key={t.name} className="inline-flex animate-pop items-center rounded-full border bg-background text-xs text-muted-foreground">
          <Link href={`/?tag=${encodeURIComponent(t.name)}`} className="py-0.5 pr-1 pl-2.5 hover:text-foreground">
            #{t.name}
          </Link>
          <button
            onClick={() => save.mutate(names.filter((n) => n !== t.name))}
            aria-label={`Remove tag ${t.name}`}
            className="mr-0.5 grid size-5 place-items-center rounded-full hover:bg-muted hover:text-foreground"
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          add();
        }}
      >
        <label htmlFor={`${listId}-input`} className="sr-only">
          Add a tag
        </label>
        <input
          id={`${listId}-input`}
          list={listId}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => draft.trim() && add()}
          placeholder="+ Add tag"
          maxLength={40}
          className="h-6 w-28 rounded-full border border-dashed bg-transparent px-2.5 text-xs outline-none placeholder:text-muted-foreground focus:w-40 focus:border-brand/60 focus:border-solid motion-safe:transition-[width,border-color] motion-safe:duration-200"
        />
        <datalist id={listId}>
          {allTags.data?.filter((t) => !names.includes(t.name)).map((t) => <option key={t.id} value={t.name} />)}
        </datalist>
      </form>
    </div>
  );
}

/** The full text inside Recall, with the cited passage (if any) highlighted and in view. */
function DocumentText({ item, chunkId, range }: { item: Item; chunkId: number | null; range: { from: number; to: number } | null }) {
  const content = useQuery({ queryKey: ["content", item.id], queryFn: () => api.content(item.id), retry: false });
  const chunk = useQuery({ queryKey: ["chunk", chunkId], queryFn: () => api.chunk(chunkId!), enabled: chunkId !== null });

  const marks = useMemo<Mark[]>(() => {
    if (content.data && range) {
      const length = joinPages(content.data.pages).length;
      if (range.to <= length) return [{ id: "cited", start: range.from, end: range.to, kind: "cited", title: "The passage your answer cited" }];
      return [];
    }
    if (!content.data || !chunk.data || chunk.data.item_id !== item.id) return [];
    let start = chunk.data.start_char;
    // Older chunks have no stored position; find the passage in the text instead.
    if (start === null) {
      const found = joinPages(content.data.pages).indexOf(chunk.data.chunk_text);
      start = found === -1 ? null : found;
    }
    if (start === null) return [];
    return [{ id: `chunk-${chunk.data.id}`, start, end: start + chunk.data.chunk_text.length, kind: "cited", title: "The passage your answer cited" }];
  }, [content.data, chunk.data, item.id, range]);

  if (content.isPending) {
    return (
      <div className="max-w-[68ch] space-y-3" aria-busy="true" aria-label="Loading the document">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-4/5" />
      </div>
    );
  }
  if (content.isError) {
    return (
      <div className="space-y-6">
        {chunkId && <CitedPassage chunkId={chunkId} item={item} />}
        <NoDetails item={item} reason="This item was saved before Recall kept the full text to read here." action="Process it again" />
      </div>
    );
  }
  return (
    <div className="space-y-6">
      {marks.length > 0 && (
        <p className="flex max-w-[68ch] items-center gap-2 text-sm text-muted-foreground">
          <Quote className="size-4 shrink-0 text-brand" aria-hidden />
          The passage your answer cited is highlighted below
          {chunk.data?.page ? `, on page ${chunk.data.page}` : ""}.
        </p>
      )}
      <HighlightReader itemId={item.id} pages={content.data.pages} cited={marks} />
    </div>
  );
}

function CitedPassage({ chunkId, item }: { chunkId: number; item: Item }) {
  const chunk = useQuery({ queryKey: ["chunk", chunkId], queryFn: () => api.chunk(chunkId) });
  if (chunk.isPending) return <Skeleton className="h-32 w-full rounded-xl" />;
  if (chunk.isError || chunk.data.item_id !== item.id) return null;
  return (
    <section aria-labelledby="passage-title" className="animate-enter rounded-xl border border-brand/25 bg-brand-soft/50 p-5">
      <h2 id="passage-title" className="mb-2 flex items-center gap-2 text-sm font-medium text-brand">
        <Quote className="size-4" aria-hidden /> The passage your answer cited{chunk.data.page ? `, page ${chunk.data.page}` : ""}
      </h2>
      <p className="max-w-[70ch] whitespace-pre-line text-[15px] leading-relaxed">{chunk.data.chunk_text}</p>
      {chunk.data.page && (
        <a
          href={sourceHref(item, item.id, chunk.data.page) ?? undefined}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex items-center gap-1 text-sm text-brand underline-offset-4 hover:underline"
        >
          Open at page {chunk.data.page} <ExternalLink className="size-3.5" />
        </a>
      )}
    </section>
  );
}

function Processing({ status }: { status: Item["status"] }) {
  const steps = ["Saved", "Reading the text", "Summarising and tagging"];
  const current = status === "queued" ? 1 : 2;
  return (
    <section aria-live="polite" className="rounded-xl border bg-card p-5">
      <p className="font-medium">Recall is reading this. It usually takes a few seconds.</p>
      <ol className="mt-4 flex flex-col gap-2 text-sm sm:flex-row sm:gap-6">
        {steps.map((step, i) => (
          <li key={step} className={i <= current ? "text-foreground" : "text-muted-foreground"}>
            <span
              className={`mr-2 inline-block size-2 rounded-full ${i < current ? "bg-brand" : i === current ? "animate-pulse bg-brand motion-reduce:animate-none" : "bg-muted-foreground/30"}`}
              aria-hidden
            />
            {step}
          </li>
        ))}
      </ol>
    </section>
  );
}

function Failed({ item }: { item: Item }) {
  const queryClient = useQueryClient();
  const retry = useMutation({
    mutationFn: () => api.reprocess(item.id),
    onSuccess: (updated) => {
      queryClient.setQueryData(["item", item.id], updated);
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
    onError: (err) => toast.error(err.message),
  });
  return (
    <section role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-5">
      <p className="font-medium">Recall couldn&apos;t read this item.</p>
      <p className="mt-1 text-sm text-muted-foreground">{item.error}</p>
      <Button className="mt-4" variant="outline" onClick={() => retry.mutate()} disabled={retry.isPending}>
        <RotateCw className={retry.isPending ? "animate-spin" : ""} /> Try again
      </Button>
    </section>
  );
}

function RenameTitle({ item, onDone }: { item: Item; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState(item.title);
  const save = useMutation({
    mutationFn: () => api.patchItem(item.id, { title: title.trim() }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["item", item.id], updated);
      queryClient.invalidateQueries({ queryKey: ["items"] });
      onDone();
    },
    onError: (err) => toast.error(err.message),
  });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (title.trim() && title.trim() !== item.title) save.mutate();
        else onDone();
      }}
    >
      <label htmlFor="rename" className="sr-only">
        Title
      </label>
      <input
        id="rename"
        autoFocus
        value={title}
        maxLength={500}
        onChange={(e) => setTitle(e.target.value)}
        onKeyDown={(e) => e.key === "Escape" && onDone()}
        onBlur={(e) => e.currentTarget.form?.requestSubmit()}
        className="w-full rounded-lg border bg-card px-2 py-1 font-heading text-3xl leading-tight font-medium outline-none focus:border-brand/60 sm:text-4xl"
      />
    </form>
  );
}

/** Rename, archive or delete. Delete asks first; archive can be undone from the toast. */
function ItemMenu({ item, onRename }: { item: Item; onRename: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const archive = useMutation({
    mutationFn: (archived: boolean) => api.patchItem(item.id, { archived }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["item", item.id], updated);
      queryClient.invalidateQueries({ queryKey: ["items"] });
      if (updated.archived) {
        toast.success("Archived. It's out of your main list but still searchable.", {
          action: { label: "Undo", onClick: () => archive.mutate(false) },
        });
      }
    },
    onError: (err) => toast.error(err.message),
  });
  const remove = useMutation({
    mutationFn: () => api.remove(item.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
      toast.success("Deleted from your library.");
      router.push("/");
    },
    onError: (err) => toast.error(err.message),
  });
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger render={<Button variant="ghost" size="icon" aria-label="More actions" />}>
          <MoreHorizontal />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-44">
          <DropdownMenuItem onClick={onRename}>
            <Pencil /> Rename
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => archive.mutate(!item.archived)}>
            <Archive /> {item.archived ? "Unarchive" : "Archive"}
          </DropdownMenuItem>
          <DropdownMenuItem variant="destructive" onClick={() => setConfirmDelete(true)}>
            <Trash2 /> Delete…
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this item?</AlertDialogTitle>
            <AlertDialogDescription>
              &ldquo;{item.title}&rdquo;, your highlights, notes and flashcards on it will be removed. This can&apos;t be undone. Archive it
              instead to keep it searchable.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => remove.mutate()} disabled={remove.isPending}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

function BackLink() {
  return (
    <Link href="/" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" /> Library
    </Link>
  );
}

function ItemSkeleton() {
  return (
    <div className="mx-auto max-w-4xl space-y-6" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-4 w-20" />
      <Skeleton className="h-10 w-3/4" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
