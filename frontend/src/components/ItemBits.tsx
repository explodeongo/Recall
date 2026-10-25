import { AlertCircle, CheckCircle2, FileText, Globe, Loader2 } from "lucide-react";
import Link from "next/link";
import type { Item, ItemStatus, SourceType, Tag } from "@/lib/api";
import { cn } from "@/lib/utils";

const statusMeta: Record<ItemStatus, { label: string; className: string; icon: React.ElementType; spin?: boolean }> = {
  queued: { label: "Queued", className: "bg-muted text-muted-foreground", icon: Loader2, spin: true },
  processing: { label: "Reading", className: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200", icon: Loader2, spin: true },
  ready: { label: "Ready", className: "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200", icon: CheckCircle2 },
  failed: { label: "Failed", className: "bg-red-100 text-red-900 dark:bg-red-950 dark:text-red-200", icon: AlertCircle },
};

export function StatusBadge({ status, className }: { status: ItemStatus; className?: string }) {
  const meta = statusMeta[status];
  const Icon = meta.icon;
  return (
    // Keyed by status, so a change (Reading to Ready) plays a short pop instead of a hard swap.
    <span key={status} className={cn("inline-flex animate-pop items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium transition-colors", meta.className, className)}>
      <Icon className={cn("size-3", meta.spin && "animate-spin motion-reduce:animate-none")} aria-hidden />
      {meta.label}
    </span>
  );
}

export function SourceIcon({ type, className }: { type: SourceType; className?: string }) {
  const Icon = type === "pdf" ? FileText : Globe;
  return <Icon className={cn("size-4 shrink-0 text-muted-foreground", className)} aria-label={type === "pdf" ? "PDF" : "Web article"} />;
}

export function sourceLabel(item: Pick<Item, "source_type" | "source">) {
  if (item.source_type === "pdf") return "PDF";
  try {
    return new URL(item.source).hostname.replace(/^www\./, "");
  } catch {
    return "Web";
  }
}

export function TagLink({ tag, active, count }: { tag: Pick<Tag, "name">; active?: boolean; count?: number }) {
  return (
    <Link
      href={active ? "/" : `/?tag=${encodeURIComponent(tag.name)}`}
      aria-pressed={active}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs transition-[color,background-color,border-color,transform] duration-150 ease-(--ease-out) active:scale-[0.97]",
        active
          ? "border-brand bg-brand text-brand-foreground"
          : "border-border bg-background text-muted-foreground hover:border-brand/50 hover:text-foreground",
      )}
    >
      #{tag.name}
      {count !== undefined && <span className={cn("tabular-nums", active ? "opacity-80" : "opacity-60")}>{count}</span>}
    </Link>
  );
}

export function timeAgo(iso: string) {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  const units: [number, Intl.RelativeTimeFormatUnit][] = [
    [60, "second"],
    [60, "minute"],
    [24, "hour"],
    [7, "day"],
    [4.35, "week"],
    [12, "month"],
    [Infinity, "year"],
  ];
  let value = -seconds;
  for (const [size, unit] of units) {
    if (Math.abs(value) < size) return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(Math.round(value), unit);
    value /= size;
  }
  return "";
}
