"use client";

import { useEffect, useMemo, useRef } from "react";
import type { Page } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface Mark {
  id: string;
  start: number;
  end: number;
  kind: "cited" | "highlight";
  title?: string;
}

interface Paragraph {
  page: number | null;
  firstOnPage: boolean;
  start: number;
  text: string;
}

/** Offsets count across pages joined by a blank line, as the backend stores them. */
export function joinPages(pages: Page[]) {
  return pages.map((p) => p.text).join("\n\n");
}

function paragraphsOf(pages: Page[]): Paragraph[] {
  const out: Paragraph[] = [];
  let offset = 0;
  pages.forEach((page, i) => {
    if (i > 0) offset += 2;
    let local = 0;
    page.text.split("\n\n").forEach((text, j) => {
      if (j > 0) local += 2;
      if (text.trim()) out.push({ page: page.page, firstOnPage: j === 0, start: offset + local, text });
      local += text.length;
    });
    offset += page.text.length;
  });
  return out;
}

/**
 * The document's full text, set for reading, with marks drawn over character ranges: the
 * passage an answer cited, and the reader's own highlights. `focus` scrolls a mark into view.
 */
export function Reader({
  pages,
  marks = [],
  focus,
  onMarkClick,
  className,
}: {
  pages: Page[];
  marks?: Mark[];
  focus?: string | null;
  onMarkClick?: (mark: Mark) => void;
  className?: string;
}) {
  const paragraphs = useMemo(() => paragraphsOf(pages), [pages]);
  const focusRef = useRef<HTMLElement | null>(null);
  const showPages = pages.some((p) => p.page !== null);

  useEffect(() => {
    // Wait a frame so the layout settles before scrolling to the passage.
    const id = requestAnimationFrame(() => focusRef.current?.scrollIntoView({ block: "center", behavior: "smooth" }));
    return () => cancelAnimationFrame(id);
  }, [focus, paragraphs]);

  let focusAssigned = false;
  return (
    <div data-reader className={cn("max-w-[68ch] font-heading text-[18px] leading-[1.75] text-pretty", className)}>
      {paragraphs.map((para) => {
        const end = para.start + para.text.length;
        const inside = marks.filter((m) => m.start < end && m.end > para.start).sort((a, b) => a.start - b.start);
        const pieces: React.ReactNode[] = [];
        let cursor = para.start;
        for (const mark of inside) {
          const from = Math.max(mark.start, cursor);
          const to = Math.min(mark.end, end);
          if (from > cursor) pieces.push(para.text.slice(cursor - para.start, from - para.start));
          if (to > from) {
            const isFocus = mark.id === focus && !focusAssigned;
            if (isFocus) focusAssigned = true;
            pieces.push(
              <mark
                key={`${mark.id}-${from}`}
                ref={isFocus ? (el) => void (focusRef.current = el) : undefined}
                data-mark={mark.id}
                title={mark.title}
                onClick={onMarkClick ? () => onMarkClick(mark) : undefined}
                className={cn(
                  "rounded-[3px] px-0.5 text-inherit [box-decoration-break:clone]",
                  mark.kind === "cited"
                    ? "bg-brand-soft underline decoration-brand decoration-2 underline-offset-4"
                    : "bg-amber-200/70 dark:bg-amber-400/25",
                  onMarkClick && "cursor-pointer",
                )}
              >
                {para.text.slice(from - para.start, to - para.start)}
              </mark>,
            );
          }
          cursor = Math.max(cursor, to);
        }
        if (cursor < end) pieces.push(para.text.slice(cursor - para.start));
        return (
          <div key={para.start}>
            {showPages && para.firstOnPage && para.page !== null && (
              <p className="mt-10 mb-3 flex items-center gap-3 font-sans text-xs text-muted-foreground tabular-nums first:mt-0" aria-label={`Page ${para.page}`}>
                <span>Page {para.page}</span>
                <span className="h-px flex-1 bg-border" aria-hidden />
              </p>
            )}
            <p data-start={para.start} className="mb-5">
              {pieces}
            </p>
          </div>
        );
      })}
    </div>
  );
}
