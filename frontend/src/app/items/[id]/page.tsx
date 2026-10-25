"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, MessageSquareText, Quote, RotateCw, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useId, useRef, useState } from "react";
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
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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
  const chunkId = Number(useSearchParams().get("chunk")) || null;
  const item = useQuery({
    queryKey: ["item", id],
    queryFn: () => api.item(id),
    refetchInterval: (query) => (query.state.data && isBusy(query.state.data.status) ? 1500 : false),
  });
  // Only an item seen being read on this visit gets the reveal; opening a finished one is instant.
  const sawProcessing = useRef(false);

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
        <h1 className="text-balance font-heading text-3xl leading-tight font-medium break-words sm:text-4xl">{data.title}</h1>
        <div className="flex flex-wrap gap-2 pt-1">
          {data.status === "ready" && (
            <Link href={`/ask?item=${data.id}`} className={cn(buttonVariants(), "bg-brand text-brand-foreground hover:bg-brand/85")}>
              <MessageSquareText /> Ask about this document
            </Link>
          )}
          <a href={sourceHref(data, data.id)} target="_blank" rel="noreferrer" className={buttonVariants({ variant: "outline" })}>
            <ExternalLink /> Open {data.source_type === "pdf" ? "PDF" : "original"}
          </a>
          <DeleteButton item={data} />
        </div>
        {data.status !== "queued" && data.status !== "processing" && <TagEditor item={data} />}
      </header>

      {chunkId && <CitedPassage chunkId={chunkId} item={data} />}

      {isBusy(data.status) && <Processing status={data.status} />}
      {data.status === "failed" && <Failed item={data} />}

      {data.summary && (
        <div className={cn("space-y-10", sawProcessing.current && "animate-develop")}>
          <p className="max-w-[65ch] font-heading text-xl leading-relaxed text-pretty">{data.summary}</p>
          {data.details ? <Details details={data.details} /> : data.status === "ready" && <NoDetails item={data} />}
        </div>
      )}
    </article>
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
function NoDetails({ item }: { item: Item }) {
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
      <span className="flex-1">This item was saved before Recall wrote full summaries.</span>
      <Button variant="outline" size="sm" onClick={() => redo.mutate()} disabled={redo.isPending}>
        <RotateCw className={redo.isPending ? "animate-spin" : ""} /> Write a full summary
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
          href={sourceHref(item, item.id, chunk.data.page)}
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

function DeleteButton({ item }: { item: Item }) {
  const router = useRouter();
  const queryClient = useQueryClient();
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
    <AlertDialog>
      <AlertDialogTrigger render={<Button variant="ghost" className="text-muted-foreground" />}>
        <Trash2 /> Delete
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete this item?</AlertDialogTitle>
          <AlertDialogDescription>
            &ldquo;{item.title}&rdquo; and everything Recall learned from it will be removed. This can&apos;t be undone.
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
