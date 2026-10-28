"use client";

import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { WAKING, useGuestStart } from "@/components/Guest";

/** The link to share (a résumé, a README): opens a fresh copy of the demo library, no sign-up. */
export default function DemoPage() {
  const { start, slow, error } = useGuestStart();
  const started = useRef(false);
  useEffect(() => {
    // Once, even when React runs effects twice in development.
    if (started.current) return;
    started.current = true;
    start();
  }, [start]);

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col items-center justify-center text-center">
      <span className="mb-5 grid size-10 place-items-center rounded-lg bg-brand font-heading text-2xl leading-none font-semibold text-brand-foreground">
        R
      </span>
      {error ? (
        <>
          <h1 className="font-heading text-2xl font-medium">The demo didn&apos;t open</h1>
          <p role="alert" className="mt-2 text-sm text-muted-foreground">
            {error}
          </p>
          <Link href="/login" className="mt-6 text-sm text-brand underline-offset-4 hover:underline">
            Go to the log-in page
          </Link>
        </>
      ) : (
        <>
          <h1 className="flex items-center gap-2 font-heading text-2xl font-medium">
            <Loader2 className="size-5 animate-spin text-brand motion-reduce:animate-none" aria-hidden />
            Opening the demo library
          </h1>
          <p aria-live="polite" className="mt-2 min-h-10 text-sm text-pretty text-muted-foreground">
            {slow ? WAKING : "A private copy, just for you."}
          </p>
        </>
      )}
    </div>
  );
}
