"use client";

import { CheckCircle2, Loader2, OctagonX } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { buttonVariants } from "@/components/ui/button";
import { api, type Item } from "@/lib/api";

/**
 * Where "Save to Recall" lands: the bookmark button (?url=&title=) and the phone's Share menu
 * (?title=&text=&url=, from the installed app's share target). A link is saved as a link;
 * shared text with no link becomes a note.
 */
export default function SavePage() {
  return (
    <Suspense>
      <Save />
    </Suspense>
  );
}

function sharedUrl(url: string | null, text: string | null): string | null {
  const candidate = url || text?.match(/https?:\/\/\S+/)?.[0] || null;
  if (!candidate) return null;
  try {
    return new URL(candidate).toString();
  } catch {
    return null;
  }
}

function Save() {
  const params = useSearchParams();
  const started = useRef(false);
  const [state, setState] = useState<{ status: "saving" } | { status: "saved"; item: Item } | { status: "error"; message: string }>({ status: "saving" });
  const url = sharedUrl(params.get("url"), params.get("text"));
  const text = params.get("text")?.trim() || "";
  const title = params.get("title")?.trim() || undefined;
  // A link saved before comes back as the old item rather than a copy.
  const saved = state.status === "saved" && Date.now() - new Date(state.item.created_at).getTime() < 60_000;

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const job = url ? api.saveUrl(url) : text ? api.saveNote(text, title) : null;
    if (!job) {
      setState({ status: "error", message: "There was nothing to save: no link and no text came through." });
      return;
    }
    job
      .then((item) => {
        setState({ status: "saved", item });
        // Opened as a small window by the bookmark button: get out of the way.
        if (window.opener) setTimeout(() => window.close(), 1800);
      })
      .catch((err: Error) => setState({ status: "error", message: err.message }));
  }, [url, text, title]);

  return (
    <div className="mx-auto flex min-h-[60vh] max-w-sm flex-col items-center justify-center text-center" aria-live="polite">
      {state.status === "saving" && (
        <>
          <Loader2 className="size-8 animate-spin text-brand motion-reduce:animate-none" aria-hidden />
          <p className="mt-4 font-medium">Saving to Recall…</p>
          <p className="mt-1 line-clamp-2 text-sm break-all text-muted-foreground">{url ?? title ?? text.slice(0, 120)}</p>
        </>
      )}
      {state.status === "saved" && (
        <div className="animate-enter">
          <CheckCircle2 className="mx-auto size-9 text-emerald-600 dark:text-emerald-400" aria-hidden />
          <h1 className="mt-4 font-heading text-2xl font-medium">{saved ? "Saved to Recall" : "Already in your library"}</h1>
          <p className="mt-2 line-clamp-2 text-sm break-words text-muted-foreground">{title ?? state.item.title}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {saved ? "It'll be summarised and tagged in a few seconds." : "You saved this link before, so nothing new was added."}
          </p>
          <div className="mt-6 flex justify-center gap-2">
            <Link href={`/items/${state.item.id}`} className={buttonVariants({ variant: "outline" })}>
              Open it
            </Link>
            <Link href="/" className={buttonVariants({ variant: "ghost" })}>
              Library
            </Link>
          </div>
        </div>
      )}
      {state.status === "error" && (
        <div className="animate-enter">
          <OctagonX className="mx-auto size-9 text-destructive" aria-hidden />
          <h1 className="mt-4 font-heading text-2xl font-medium">Couldn&apos;t save that</h1>
          <p role="alert" className="mt-2 text-sm text-muted-foreground">
            {state.message}
          </p>
          <Link href="/add" className={buttonVariants({ variant: "outline", className: "mt-6" })}>
            Add it by hand
          </Link>
        </div>
      )}
    </div>
  );
}
