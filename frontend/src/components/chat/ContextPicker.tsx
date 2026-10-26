"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen, Globe, Library, X } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { SourceIcon, tagStyle } from "@/components/ItemBits";
import { api, type AnswerSource, type MessageContext } from "@/lib/api";
import { cn } from "@/lib/utils";

export type Pinned = Pick<MessageContext, "items" | "tags">;

export type Mention = { kind: "item"; id: number; title: string } | { kind: "tag"; name: string };

/** The "@" query being typed at the caret, if any: "@" at the start or after a space. */
export function mentionAt(text: string, caret: number): { start: number; query: string } | null {
  const before = text.slice(0, caret);
  const match = /(^|\s)@([^\s@]{0,40})$/.exec(before);
  return match ? { start: before.length - match[2].length - 1, query: match[2] } : null;
}

/** Items and tags matching `query`, for the "@" menu: tags first, then items. */
export function useMentions(query: string, pinned: Pinned, open: boolean): Mention[] {
  const items = useQuery({ queryKey: ["mention-items"], queryFn: () => api.items(), enabled: open, staleTime: 60_000 });
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags, enabled: open });
  return useMemo(() => {
    const q = query.toLowerCase();
    const pinnedIds = new Set(pinned.items.map((i) => i.id));
    const tagMatches: Mention[] = (tags.data ?? [])
      .filter((t) => t.item_count > 0 && !pinned.tags.includes(t.name) && t.name.includes(q))
      .slice(0, 4)
      .map((t) => ({ kind: "tag", name: t.name }));
    const itemMatches: Mention[] = (items.data ?? [])
      .filter((i) => i.status === "ready" && !pinnedIds.has(i.id) && i.title.toLowerCase().includes(q))
      .slice(0, 6)
      .map((i) => ({ kind: "item", id: i.id, title: i.title }));
    return [...tagMatches, ...itemMatches];
  }, [query, pinned, items.data, tags.data]);
}

/** The "@" menu, shown above the question box. Keyboard handling lives in the composer. */
export function MentionMenu({
  options,
  active,
  onPick,
  query,
  anchor,
}: {
  options: Mention[];
  active: number;
  onPick: (m: Mention) => void;
  query: string;
  /** The question box: the menu opens on whichever side of it has room. */
  anchor: React.RefObject<HTMLElement | null>;
}) {
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags });
  const items = useQuery({ queryKey: ["mention-items"], queryFn: () => api.items(), staleTime: 60_000 });
  const colors = new Map((tags.data ?? []).map((t) => [t.name, t.color]));
  const kinds = new Map((items.data ?? []).map((i) => [i.id, i.source_type]));
  const list = useRef<HTMLDivElement>(null);
  const [place, setPlace] = useState<{ side: "above" | "below"; max: number }>({ side: "above", max: 320 });

  // Open above the box when there's room under the nav bar, otherwise below it, and never
  // taller than the space on that side (the rest scrolls).
  useLayoutEffect(() => {
    const measure = () => {
      const rect = anchor.current?.getBoundingClientRect();
      if (!rect) return;
      const nav = document.querySelector("header")?.getBoundingClientRect().bottom ?? 0;
      const above = rect.top - nav - 16;
      const below = window.innerHeight - rect.bottom - 16;
      const side = above >= 240 || above >= below ? "above" : "below";
      setPlace({ side, max: Math.max(140, Math.min(360, side === "above" ? above : below)) });
    };
    measure();
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => {
      window.removeEventListener("resize", measure);
      window.removeEventListener("scroll", measure, true);
    };
  }, [anchor]);

  // Keep the highlighted option in view as the arrow keys move it.
  useEffect(() => {
    list.current?.querySelector(`#mention-${active}`)?.scrollIntoView({ block: "nearest" });
  }, [active]);

  return (
    <div
      ref={list}
      id="mention-menu"
      role="listbox"
      aria-label="Limit the answer to"
      style={{ maxHeight: place.max }}
      className={cn(
        "absolute right-2 left-2 z-20 animate-enter overflow-y-auto overscroll-contain rounded-xl border bg-popover p-1 text-popover-foreground shadow-lg",
        place.side === "above" ? "bottom-full mb-2" : "top-full mt-2",
      )}
    >
      <p className="sticky -top-1 z-10 -mx-1 -mt-1 bg-popover px-3.5 pt-2.5 pb-1 text-xs text-muted-foreground">Answer only from…</p>
      {options.length === 0 ? (
        <p className="px-2.5 py-2 text-sm text-muted-foreground">{query ? `Nothing in your library matches “${query}”.` : "Nothing to pin yet."}</p>
      ) : (
        options.map((m, i) => (
          <button
            key={m.kind === "tag" ? `t-${m.name}` : `i-${m.id}`}
            id={`mention-${i}`}
            type="button"
            role="option"
            aria-selected={i === active}
            // Keep focus in the question box.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => onPick(m)}
            className={cn("flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm", i === active && "bg-muted")}
          >
            {m.kind === "tag" ? (
              <>
                <span className="size-2.5 shrink-0 rounded-full" style={{ background: colors.get(m.name) ?? "#8d8d86" }} aria-hidden />
                <span>#{m.name}</span>
                <span className="ml-auto text-xs text-muted-foreground">every item tagged</span>
              </>
            ) : (
              <>
                <SourceIcon type={kinds.get(m.id) ?? "url"} className="size-3.5" />
                <span className="min-w-0 truncate">{m.title}</span>
              </>
            )}
          </button>
        ))
      )}
    </div>
  );
}

/** What the next answer is limited to, as removable chips. */
export function PinnedChips({ pinned, onRemove }: { pinned: Pinned; onRemove?: (m: Mention) => void }) {
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags });
  const colors = new Map((tags.data ?? []).map((t) => [t.name, t.color]));
  if (!pinned.items.length && !pinned.tags.length) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Answer limited to">
      {pinned.tags.map((name) => (
        <span key={name} style={tagStyle(colors.get(name) ?? "#8d8d86")} className="tag-chip inline-flex animate-pop items-center gap-1 rounded-full border py-0.5 pr-1 pl-2 text-xs">
          #{name}
          {onRemove && <RemoveButton label={`Stop limiting to #${name}`} onClick={() => onRemove({ kind: "tag", name })} />}
        </span>
      ))}
      {pinned.items.map((item) => (
        <span key={item.id} className="inline-flex max-w-64 animate-pop items-center gap-1 rounded-full border bg-background py-0.5 pr-1 pl-2 text-xs">
          <BookOpen className="size-3 shrink-0 text-muted-foreground" aria-hidden />
          <span className="truncate">{item.title}</span>
          {onRemove && <RemoveButton label={`Stop limiting to ${item.title}`} onClick={() => onRemove({ kind: "item", ...item })} />}
        </span>
      ))}
    </div>
  );
}

function RemoveButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} aria-label={label} className="grid size-4 place-items-center rounded-full opacity-70 hover:bg-foreground/10 hover:opacity-100">
      <X className="size-3" />
    </button>
  );
}

const SOURCES: { id: AnswerSource; label: string; short: string; icon: typeof Globe; hint: string }[] = [
  { id: "library", label: "Library", short: "Library", icon: Library, hint: "Answers only from what you've saved" },
  { id: "both", label: "Library + Web", short: "Both", icon: Globe, hint: "Your library first, the web for what it doesn't cover" },
  { id: "web", label: "Web", short: "Web", icon: Globe, hint: "Skip your library and answer from the web" },
];

/** Where answers may come from. */
export function SourceSwitch({ value, onChange }: { value: AnswerSource; onChange: (s: AnswerSource) => void }) {
  return (
    <div role="radiogroup" aria-label="Answer from" className="flex rounded-full border p-0.5 text-xs">
      {SOURCES.map((s) => (
        <button
          key={s.id}
          type="button"
          role="radio"
          aria-checked={value === s.id}
          aria-label={s.label}
          title={s.hint}
          onClick={() => onChange(s.id)}
          className={cn(
            "rounded-full px-2.5 py-0.5 transition-[color,background-color] duration-150",
            value === s.id ? "bg-brand-soft font-medium text-brand" : "text-muted-foreground hover:text-foreground",
          )}
        >
          <span className="hidden sm:inline">{s.label}</span>
          <span className="sm:hidden">{s.short}</span>
        </button>
      ))}
    </div>
  );
}

/** The answer source, remembered per browser (the older on/off web switch carries over). */
export function useAnswerSource(): [AnswerSource, (s: AnswerSource) => void] {
  const [source, setSource] = useState<AnswerSource>("both");
  useEffect(() => {
    try {
      const saved = localStorage.getItem("recall-source");
      if (saved === "library" || saved === "both" || saved === "web") setSource(saved);
      else if (localStorage.getItem("recall-web") === "off") setSource("library");
    } catch {}
  }, []);
  return [
    source,
    (next) => {
      setSource(next);
      try {
        localStorage.setItem("recall-source", next);
      } catch {}
    },
  ];
}
