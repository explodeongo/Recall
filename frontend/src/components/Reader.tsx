"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef } from "react";
import { Figure } from "@/components/Pictures";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { imageSrc, passageHref, type LinkedIdea, type Page, type Picture } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface Mark {
  id: string;
  start: number;
  end: number;
  kind: "cited" | "highlight" | "link";
  title?: string;
  /** For "link" marks: the saved items this term is about. */
  link?: LinkedIdea;
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
/** For each paragraph, the pictures that go after it: by their place in the text, or at the
 * end of their page when they have no place. */
function figuresByParagraph(paragraphs: Paragraph[], figures: Picture[]) {
  const after = new Map<number, Picture[]>();
  for (const figure of figures) {
    let index = paragraphs.length - 1;
    if (figure.position != null) {
      const found = paragraphs.findIndex((p) => p.start + p.text.length >= figure.position!);
      if (found !== -1) index = found;
    } else if (figure.page != null) {
      const onPage = paragraphs.map((p, i) => (p.page === figure.page ? i : -1)).filter((i) => i !== -1);
      if (onPage.length) index = onPage[onPage.length - 1];
    }
    after.set(index, [...(after.get(index) ?? []), figure]);
  }
  return after;
}

export function Reader({
  pages,
  marks = [],
  links = [],
  figures = [],
  focus,
  onMarkClick,
  className,
}: {
  pages: Page[];
  marks?: Mark[];
  /** Linked ideas: terms other saved items are about, drawn where they don't overlap a mark. */
  links?: LinkedIdea[];
  figures?: Picture[];
  focus?: string | null;
  onMarkClick?: (mark: Mark) => void;
  className?: string;
}) {
  const paragraphs = useMemo(() => paragraphsOf(pages), [pages]);
  const placed = useMemo(() => figuresByParagraph(paragraphs, figures), [paragraphs, figures]);
  const allMarks = useMemo(() => {
    const free = links.filter((l) => !marks.some((m) => m.start < l.end && m.end > l.start));
    const linked: Mark[] = free.map((l) => ({ id: `l-${l.start}`, start: l.start, end: l.end, kind: "link", link: l }));
    return [...marks, ...linked];
  }, [marks, links]);
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
      {paragraphs.map((para, index) => {
        const end = para.start + para.text.length;
        const inside = allMarks.filter((m) => m.start < end && m.end > para.start).sort((a, b) => a.start - b.start);
        const pieces: React.ReactNode[] = [];
        let cursor = para.start;
        for (const mark of inside) {
          const from = Math.max(mark.start, cursor);
          const to = Math.min(mark.end, end);
          if (from > cursor) pieces.push(para.text.slice(cursor - para.start, from - para.start));
          if (to > from && mark.kind === "link" && mark.link) {
            pieces.push(<LinkedTerm key={`${mark.id}-${from}`} idea={mark.link} text={para.text.slice(from - para.start, to - para.start)} />);
          } else if (to > from) {
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
            {placed.get(index)?.map((figure) => <Figure key={figure.id} picture={figure} className="font-sans" />)}
          </div>
        );
      })}
    </div>
  );
}

/** A term other saved items are about: hover (or tap) to see them and the passage that
 * mentions it in each. */
function LinkedTerm({ idea, text }: { idea: LinkedIdea; text: string }) {
  return (
    <Popover>
      {/* A span, not a button: the term sits inside a sentence. Base UI adds the keyboard handling. */}
      <PopoverTrigger
        nativeButton={false}
        openOnHover
        delay={250}
        render={
          <span
            role="button"
            tabIndex={0}
            className="cursor-pointer rounded-[3px] underline decoration-brand/60 decoration-dotted decoration-2 underline-offset-[5px] transition-colors duration-150 hover:bg-brand-soft/60 hover:decoration-brand data-popup-open:bg-brand-soft/60"
          />
        }
      >
        {text}
      </PopoverTrigger>
      <PopoverContent side="top" align="center" className="w-80 p-2 font-sans">
        <p className="px-2 pt-1 pb-1.5 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">{idea.term}</span> in your library
        </p>
        <ul className="space-y-1">
          {idea.targets.map((t) => (
            <li key={t.item_id}>
              <Link
                href={
                  t.chunk_id !== null
                    ? passageHref({ item_id: t.item_id, chunk_id: t.chunk_id, start_char: t.start_char, end_char: t.end_char, kind: "text" })
                    : `/items/${t.item_id}`
                }
                className="flex gap-2.5 rounded-lg p-2 transition-colors duration-150 hover:bg-muted"
              >
                {t.cover_url ? (
                  // eslint-disable-next-line @next/next/no-img-element -- served by the API
                  <img src={imageSrc(t.cover_url)} alt="" className="size-10 shrink-0 rounded-md border bg-muted object-cover" />
                ) : (
                  <span className="grid size-10 shrink-0 place-items-center rounded-md bg-brand-soft text-sm font-semibold text-brand" aria-hidden>
                    {t.title.trim()[0]?.toUpperCase()}
                  </span>
                )}
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{t.title}</span>
                  {t.snippet && <span className="mt-0.5 line-clamp-2 block text-xs leading-snug text-muted-foreground">{t.snippet}</span>}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
