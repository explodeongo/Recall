"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Quote, RotateCw, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useRef } from "react";
import { toast } from "sonner";
import { SourceIcon, StatusBadge, TagLink, sourceLabel, timeAgo } from "@/components/ItemBits";
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
import { api, isBusy, sourceHref, type Item } from "@/lib/api";
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
      <div className="space-y-4">
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
    <article className="space-y-8">
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
          <a href={sourceHref(data, data.id)} target="_blank" rel="noreferrer" className={buttonVariants({ variant: "outline" })}>
            <ExternalLink /> Open {data.source_type === "pdf" ? "PDF" : "original"}
          </a>
          <DeleteButton item={data} />
        </div>
      </header>

      {chunkId && <CitedPassage chunkId={chunkId} item={data} />}

      {isBusy(data.status) && <Processing status={data.status} />}
      {data.status === "failed" && <Failed item={data} />}

      {data.summary && (
        <section aria-labelledby="summary" className={cn("space-y-2", sawProcessing.current && "animate-develop")}>
          <h2 id="summary" className="text-sm font-medium text-muted-foreground">
            Summary
          </h2>
          <p className="max-w-[65ch] font-heading text-xl leading-relaxed">{data.summary}</p>
        </section>
      )}

      {data.tags.length > 0 && (
        <section aria-label="Tags" className={cn("flex flex-wrap gap-1.5", sawProcessing.current && "animate-enter [--i:4]")}>
          {data.tags.map((t) => (
            <TagLink key={t.id} tag={t} />
          ))}
        </section>
      )}

      {data.status === "ready" && (
        <Link href="/ask" className={buttonVariants({ variant: "secondary" })}>
          Ask a question about your library
        </Link>
      )}
    </article>
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
    <div className="space-y-6" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-4 w-20" />
      <Skeleton className="h-10 w-3/4" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
