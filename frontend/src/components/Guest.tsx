"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/** True once `active` has lasted `ms`: a free server waking from sleep takes up to a minute,
 *  and saying so beats a spinner that seems stuck. */
export function useSlow(active: boolean, ms = 3500) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!active) {
      setSlow(false);
      return;
    }
    const timer = setTimeout(() => setSlow(true), ms);
    return () => clearTimeout(timer);
  }, [active, ms]);
  return slow;
}

export const WAKING = "Waking up the server. After a quiet spell this takes up to a minute.";

/** Start a guest session on a fresh copy of the demo library, then open it. */
export function useGuestStart() {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const slow = useSlow(busy);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      const user = await api.startGuest();
      queryClient.setQueryData(["me"], user);
      // A full navigation, so the server sees the new session cookie.
      window.location.assign("/");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }
  return { start, busy, slow, error };
}

/** On the log-in page, when this server offers the demo. */
export function DemoCard({ hours }: { hours: number }) {
  const { start, busy, slow, error } = useGuestStart();
  return (
    <div className="mb-6">
      <div className="rounded-2xl border bg-card p-5 shadow-xs">
        <h2 className="font-heading text-lg font-medium">Try it with a full library</h2>
        <p className="mt-1 text-sm text-pretty text-muted-foreground">
          Thirty papers, articles and lectures, already read, with chats and flashcards. No sign-up: it&apos;s yours for{" "}
          {hours === 24 ? "a day" : `${hours} hours`}, and nobody else sees what you do.
        </p>
        <Button onClick={start} disabled={busy} size="lg" className="mt-4 h-10 w-full bg-brand text-brand-foreground hover:bg-brand/85">
          {busy && <Loader2 className="animate-spin motion-reduce:animate-none" />}
          {busy ? "Opening the demo…" : "Try the demo"}
        </Button>
        <p aria-live="polite" className="mt-2 text-xs text-muted-foreground empty:hidden">
          {slow ? WAKING : null}
        </p>
        {error && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
      <div className="mt-6 flex items-center gap-3 text-xs text-muted-foreground" aria-hidden>
        <span className="h-px flex-1 bg-border" />
        or log in
        <span className="h-px flex-1 bg-border" />
      </div>
    </div>
  );
}

/** A slim bar under the navigation while a guest is looking around. */
export function GuestBanner() {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity });
  if (!me.data?.is_guest) return null;
  return (
    <div className="border-t bg-brand-soft/60 px-4 py-1.5 text-center text-xs text-pretty text-foreground/80 sm:text-[13px]">
      <span className="font-medium text-foreground">This is your own copy of the demo library.</span> Save, ask and quiz freely;
      nobody else sees it.
    </div>
  );
}
