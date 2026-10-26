"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Check, Flame, Layers, X } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type CardStage, type DueCard, type Grade } from "@/lib/api";
import { cn } from "@/lib/utils";

const GRADES: { grade: Grade; label: string; key: string; tone: string }[] = [
  { grade: "again", label: "Again", key: "1", tone: "hover:border-red-400/60 hover:bg-red-500/5" },
  { grade: "hard", label: "Hard", key: "2", tone: "hover:border-amber-400/60 hover:bg-amber-500/5" },
  { grade: "good", label: "Good", key: "3", tone: "hover:border-emerald-400/60 hover:bg-emerald-500/5" },
  { grade: "easy", label: "Easy", key: "4", tone: "hover:border-sky-400/60 hover:bg-sky-500/5" },
];

const STAGES: Record<CardStage, { label: string; className: string }> = {
  new: { label: "New", className: "bg-brand-soft text-brand" },
  learning: { label: "Learning", className: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200" },
  practiced: { label: "Practiced", className: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" },
  confident: { label: "Confident", className: "bg-sky-100 text-sky-900 dark:bg-sky-950 dark:text-sky-200" },
  mastered: { label: "Mastered", className: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200" },
};

export default function ReviewPage() {
  return (
    <Suspense>
      <Review />
    </Suspense>
  );
}

function Review() {
  const itemId = Number(useSearchParams().get("item")) || undefined;
  // The queue is fixed when the session starts, so cards don't jump around while reviewing.
  const due = useQuery({ queryKey: ["review-queue", itemId ?? null], queryFn: () => api.dueCards(itemId), staleTime: Infinity, refetchOnWindowFocus: false });
  const stats = useQuery({ queryKey: ["review-stats"], queryFn: api.reviewStats });

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-heading text-4xl font-medium">{itemId ? "Quiz" : "Review"}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {itemId && due.data?.[0] ? `Every card from “${due.data[0].item_title}”` : "Cards come back just before you'd forget them."}
          </p>
        </div>
        {stats.data && stats.data.total > 0 && (
          <dl className="flex gap-5 text-sm">
            <div className="flex items-center gap-1.5" title="Days in a row with at least one review">
              <Flame className={cn("size-4", stats.data.streak_days ? "text-orange-500" : "text-muted-foreground")} aria-hidden />
              <dt className="sr-only">Streak</dt>
              <dd className="tabular-nums">
                {stats.data.streak_days} {stats.data.streak_days === 1 ? "day" : "days"}
              </dd>
            </div>
            <div className="flex items-center gap-1.5">
              <Layers className="size-4 text-muted-foreground" aria-hidden />
              <dt className="sr-only">Reviewed today</dt>
              <dd className="tabular-nums">{stats.data.reviewed_today} today</dd>
            </div>
          </dl>
        )}
      </header>

      {due.isPending ? (
        <Skeleton className="h-64 w-full rounded-2xl" />
      ) : due.isError ? (
        <p role="alert" className="text-muted-foreground">
          {due.error.message}
        </p>
      ) : (
        <Session cards={due.data} totalCards={stats.data?.total ?? null} nextDue={stats.data?.next_due_at ?? null} />
      )}
    </div>
  );
}

function Session({ cards, totalCards, nextDue }: { cards: DueCard[]; totalCards: number | null; nextDue: string | null }) {
  const queryClient = useQueryClient();
  const [queue, setQueue] = useState(cards);
  const [revealed, setRevealed] = useState(false);
  // For choice questions: the option picked. Picking reveals the answer.
  const [picked, setPicked] = useState<string | null>(null);
  const [done, setDone] = useState(0);
  const card = queue[0];
  const choice = !!card?.options?.length && card.kind !== "flashcard";
  const correct = picked !== null && picked === card?.answer;

  const review = useMutation({
    mutationFn: ({ id, grade }: { id: number; grade: Grade }) => api.reviewCard(id, grade),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["review-stats"] }),
    onError: (err) => toast.error(err.message),
  });

  const grade = useCallback(
    (g: Grade) => {
      if (!card || !revealed) return;
      review.mutate({ id: card.id, grade: g });
      setRevealed(false);
      setPicked(null);
      setDone((n) => n + 1);
      // A missed card comes back at the end of this session, as in Anki's learning steps.
      setQueue(([first, ...rest]) => (g === "again" ? [...rest, first] : rest));
    },
    [card, revealed, review],
  );

  // A choice question grades itself: right is "good", wrong comes back soon.
  const pick = useCallback(
    (option: string) => {
      if (!card || revealed) return;
      setPicked(option);
      setRevealed(true);
    },
    [card, revealed],
  );
  const next = useCallback(() => grade(correct ? "good" : "again"), [grade, correct]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName === "TEXTAREA" || (e.target as HTMLElement).tagName === "INPUT") return;
      if (choice && card) {
        const n = Number(e.key);
        if (!revealed && n >= 1 && n <= card.options!.length) pick(card.options![n - 1]);
        if (revealed && (e.key === "Enter" || e.key === " ")) {
          e.preventDefault();
          next();
        }
        return;
      }
      if (e.key === " " && !revealed && card) {
        e.preventDefault();
        setRevealed(true);
      }
      const match = GRADES.find((x) => x.key === e.key);
      if (match) grade(match.grade);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [revealed, card, grade, choice, pick, next]);

  if (!card) {
    return <AllDone reviewed={done} hasCards={(totalCards ?? cards.length) > 0} nextDue={nextDue} />;
  }

  const total = done + queue.length;
  return (
    <section aria-label="Flashcard" className="space-y-6">
      <div className="space-y-2">
        <div className="flex justify-between text-xs text-muted-foreground tabular-nums">
          <span>
            Card {done + 1} of {total}
          </span>
          <Link href={`/items/${card.item_id}`} className="max-w-[60%] truncate hover:text-foreground">
            {card.item_title}
          </Link>
        </div>
        <div className="h-1 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={done}>
          <div className="h-full rounded-full bg-brand transition-[width] duration-300 ease-(--ease-out)" style={{ width: `${(done / total) * 100}%` }} />
        </div>
      </div>

      <div key={`${card.id}-${done}`} className="animate-enter rounded-2xl border bg-card p-8 shadow-xs">
        <div className="mb-4 flex items-center gap-2 text-xs">
          <span className={cn("rounded-full px-2 py-0.5 font-medium", STAGES[card.stage].className)}>{STAGES[card.stage].label}</span>
          <span className="text-muted-foreground">{card.kind === "true_false" ? "True or false?" : card.kind === "multiple_choice" ? "Pick one" : "Recall it"}</span>
        </div>
        <p className="font-heading text-2xl leading-snug text-balance">{card.question}</p>
        {choice && (
          <div className={cn("mt-6 grid gap-2", card.kind === "true_false" && "grid-cols-2")} role="group" aria-label="Answers">
            {card.options!.map((option, i) => {
              const isAnswer = option === card.answer;
              const isPicked = option === picked;
              return (
                <button
                  key={option}
                  onClick={() => pick(option)}
                  disabled={revealed}
                  aria-pressed={isPicked}
                  className={cn(
                    "flex items-center gap-3 rounded-xl border px-4 py-3 text-left text-[15px] transition-[background-color,border-color,opacity,transform] duration-150 ease-(--ease-out) enabled:hover:border-brand/50 enabled:hover:bg-muted/50 enabled:active:scale-[0.99]",
                    revealed && isAnswer && "border-emerald-500/70 bg-emerald-500/10",
                    revealed && isPicked && !isAnswer && "border-red-500/70 bg-red-500/10",
                    revealed && !isAnswer && !isPicked && "opacity-50",
                  )}
                >
                  <kbd className="grid size-6 shrink-0 place-items-center rounded-md border bg-muted font-sans text-xs text-muted-foreground">{i + 1}</kbd>
                  <span className="flex-1">{option}</span>
                  {revealed && isAnswer && <Check className="size-4 animate-pop text-emerald-600 dark:text-emerald-400" aria-label="Right answer" />}
                  {revealed && isPicked && !isAnswer && <X className="size-4 animate-pop text-red-600 dark:text-red-400" aria-label="Your answer" />}
                </button>
              );
            })}
          </div>
        )}
        {revealed ? (
          <div className="mt-6 animate-enter border-t pt-6">
            {choice ? (
              <p className={cn("font-medium", correct ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400")} role="status">
                {correct ? "Right." : `Not quite. The answer is “${card.answer}”.`}
              </p>
            ) : (
              <p className="text-[17px] leading-relaxed">{card.answer}</p>
            )}
            {card.explanation && <p className="mt-2 leading-relaxed text-muted-foreground">{card.explanation}</p>}
            {card.start_char !== null && card.end_char !== null && (
              <Link
                href={`/items/${card.item_id}?from=${card.start_char}&to=${card.end_char}`}
                className="mt-4 inline-flex items-center gap-1.5 text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
              >
                <BookOpen className="size-4" aria-hidden /> See it in the text
              </Link>
            )}
          </div>
        ) : choice ? null : (
          <Button className="mt-8 w-full" size="lg" variant="outline" onClick={() => setRevealed(true)}>
            Show answer <kbd className="ml-2 rounded border bg-muted px-1.5 font-sans text-[11px] text-muted-foreground">Space</kbd>
          </Button>
        )}
      </div>

      {revealed && choice && (
        <Button className="w-full animate-enter" size="lg" onClick={next} autoFocus>
          Next <span className="ml-1 text-xs opacity-70">· back in {card.next[correct ? "good" : "again"]}</span>
          <kbd className="ml-2 rounded border border-current/20 px-1.5 font-sans text-[11px] opacity-70">Enter</kbd>
        </Button>
      )}

      {revealed && !choice && (
        <div className="grid animate-enter grid-cols-2 gap-2 sm:grid-cols-4" role="group" aria-label="How well did you remember it?">
          {GRADES.map(({ grade: g, label, key, tone }) => (
            <button
              key={g}
              onClick={() => grade(g)}
              className={cn(
                "flex flex-col items-center gap-0.5 rounded-xl border bg-card px-3 py-3 text-sm font-medium transition-[background-color,border-color,transform] duration-150 active:scale-[0.97]",
                tone,
              )}
            >
              {label}
              <span className="text-xs font-normal text-muted-foreground tabular-nums">
                {card.next[g]} · {key}
              </span>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function AllDone({ reviewed, hasCards, nextDue }: { reviewed: number; hasCards: boolean; nextDue: string | null }) {
  if (!hasCards) {
    return (
      <div className="rounded-2xl border border-dashed p-8 text-center">
        <Layers className="mx-auto size-6 text-muted-foreground" aria-hidden />
        <p className="mt-3 font-medium">No flashcards yet</p>
        <p className="mx-auto mt-1 max-w-sm text-sm text-muted-foreground">
          Open anything in your library and press <span className="font-medium text-foreground">Quiz me</span>. Recall writes
          questions from it and brings them back here over the following days.
        </p>
        <Link href="/" className={buttonVariants({ variant: "outline", className: "mt-5" })}>
          Go to the library
        </Link>
      </div>
    );
  }
  return (
    <div className="animate-enter rounded-2xl border bg-card p-8 text-center">
      <p className="font-heading text-2xl">{reviewed ? "Done for now" : "All caught up"}</p>
      <p className="mt-2 text-sm text-muted-foreground">
        {reviewed ? `You reviewed ${reviewed} ${reviewed === 1 ? "card" : "cards"}. ` : ""}
        {nextDue ? `The next card is due ${dueIn(nextDue)}.` : ""}
      </p>
      <Link href="/" className={buttonVariants({ variant: "outline", className: "mt-5" })}>
        Back to the library
      </Link>
    </div>
  );
}

function dueIn(iso: string) {
  const minutes = Math.max(1, Math.round((new Date(iso).getTime() - Date.now()) / 60000));
  if (minutes < 60) return `in ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `in ${hours} ${hours === 1 ? "hour" : "hours"}`;
  const days = Math.round(hours / 24);
  return days === 1 ? "tomorrow" : `in ${days} days`;
}

