"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Highlighter, MessageSquarePlus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { type Mark, Reader } from "@/components/Reader";
import { Button } from "@/components/ui/button";
import { api, type Highlight, type Page } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Selection {
  start: number;
  end: number;
  top: number;
  left: number;
}

/** A character offset in the document for a point in the reader (see Reader's data-start). */
function offsetOf(node: Node, offset: number): number | null {
  const el = (node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement)?.closest<HTMLElement>("[data-start]");
  if (!el) return null;
  const range = document.createRange();
  range.setStart(el, 0);
  range.setEnd(node, offset);
  return Number(el.dataset.start) + range.toString().length;
}

/**
 * The reader with highlighting: select text to highlight it (with an optional note), click a
 * highlight to edit or remove it. Highlights are listed beside the text.
 */
export function HighlightReader({ itemId, pages, cited }: { itemId: number; pages: Page[]; cited: Mark[] }) {
  const queryClient = useQueryClient();
  const container = useRef<HTMLDivElement>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [editing, setEditing] = useState<{ id: number | null; start: number; end: number; note: string } | null>(null);
  const [focus, setFocus] = useState<string | null>(cited[0]?.id ?? null);
  const highlights = useQuery({ queryKey: ["highlights", itemId], queryFn: () => api.highlights(itemId) });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["highlights", itemId] });
    queryClient.invalidateQueries({ queryKey: ["all-highlights"] });
  };
  const add = useMutation({
    mutationFn: (h: { start: number; end: number; note?: string }) => api.addHighlight(itemId, h.start, h.end, h.note),
    onSuccess: () => {
      refresh();
      window.getSelection()?.removeAllRanges();
    },
    onError: (err) => toast.error(err.message),
  });
  const edit = useMutation({
    mutationFn: (h: { id: number; note: string }) => api.editHighlight(h.id, h.note),
    onSuccess: refresh,
    onError: (err) => toast.error(err.message),
  });
  const remove = useMutation({
    mutationFn: (id: number) => api.deleteHighlight(id),
    onSuccess: refresh,
    onError: (err) => toast.error(err.message),
  });

  // Follow the browser's selection (mouse, keyboard and touch all end up here).
  const readSelection = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount || !container.current) return setSelection(null);
    const range = sel.getRangeAt(0);
    if (!container.current.contains(range.commonAncestorContainer)) return setSelection(null);
    const a = offsetOf(range.startContainer, range.startOffset);
    const b = offsetOf(range.endContainer, range.endOffset);
    if (a === null || b === null || b - a < 2) return setSelection(null);
    const rect = range.getBoundingClientRect();
    const host = container.current.getBoundingClientRect();
    setSelection({ start: a, end: b, top: rect.top - host.top, left: rect.left - host.left + rect.width / 2 });
  }, []);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const onChange = () => {
      clearTimeout(timer);
      timer = setTimeout(readSelection, 120);
    };
    document.addEventListener("selectionchange", onChange);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("selectionchange", onChange);
    };
  }, [readSelection]);

  const marks = useMemo<Mark[]>(
    () => [
      ...cited,
      ...(highlights.data ?? []).map((h) => ({ id: `h-${h.id}`, start: h.start_char, end: h.end_char, kind: "highlight" as const, title: h.note ?? "Your highlight" })),
    ],
    [cited, highlights.data],
  );

  const openEditor = (h: Highlight) => setEditing({ id: h.id, start: h.start_char, end: h.end_char, note: h.note ?? "" });

  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_16rem]">
      <div ref={container} className="relative">
        <Reader
          pages={pages}
          marks={marks}
          focus={focus}
          onMarkClick={(mark) => {
            const h = highlights.data?.find((x) => `h-${x.id}` === mark.id);
            if (h) openEditor(h);
          }}
        />
        {selection && !editing && (
          <div
            role="toolbar"
            aria-label="Highlight the selected text"
            style={{ top: selection.top, left: selection.left }}
            className="absolute z-20 flex -translate-x-1/2 -translate-y-[calc(100%+8px)] animate-pop items-center gap-0.5 rounded-lg border bg-popover p-1 shadow-md"
            onMouseDown={(e) => e.preventDefault() /* keep the selection while clicking */}
          >
            <Button size="sm" variant="ghost" onClick={() => add.mutate({ start: selection.start, end: selection.end })}>
              <Highlighter /> Highlight
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setEditing({ id: null, start: selection.start, end: selection.end, note: "" })}>
              <MessageSquarePlus /> Add note
            </Button>
          </div>
        )}
      </div>

      <aside aria-label="Your highlights" className="space-y-3 lg:sticky lg:top-22 lg:max-h-[calc(100vh-7rem)] lg:self-start lg:overflow-y-auto">
        <h2 className="text-sm font-medium text-muted-foreground">Your highlights</h2>
        {editing && (
          <NoteEditor
            key={`${editing.id}-${editing.start}`}
            initial={editing.note}
            isNew={editing.id === null}
            onCancel={() => setEditing(null)}
            onDelete={editing.id === null ? undefined : () => {
              remove.mutate(editing.id!);
              setEditing(null);
            }}
            onSave={(note) => {
              if (editing.id === null) add.mutate({ start: editing.start, end: editing.end, note });
              else edit.mutate({ id: editing.id, note });
              setEditing(null);
            }}
          />
        )}
        {highlights.data && highlights.data.length === 0 && !editing && (
          <p className="text-sm text-muted-foreground">Select any text to highlight it or add a note. Your notes become part of what Ask can answer from.</p>
        )}
        <ul className="space-y-2">
          {highlights.data?.map((h) => (
            <li
              key={h.id}
              className={cn(
                "rounded-lg border bg-card p-3 text-sm transition-colors duration-150 hover:border-amber-400/60",
                focus === `h-${h.id}` && "border-amber-400/70",
              )}
            >
              <button
                onClick={() => {
                  setFocus(null);
                  requestAnimationFrame(() => setFocus(`h-${h.id}`));
                }}
                className="block w-full text-left"
                aria-label={`Show in the text: ${h.quote.slice(0, 80)}`}
              >
                <span className="line-clamp-3 font-heading text-[15px] leading-snug">
                  <span className="rounded-sm bg-amber-200/60 px-0.5 [box-decoration-break:clone] dark:bg-amber-400/20">{h.quote}</span>
                </span>
                {h.note && <span className="mt-2 block text-muted-foreground">{h.note}</span>}
              </button>
              <button onClick={() => openEditor(h)} className="mt-1.5 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
                {h.note ? "Edit note" : "Add a note"}
              </button>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}

function NoteEditor({
  initial,
  isNew,
  onSave,
  onCancel,
  onDelete,
}: {
  initial: string;
  isNew: boolean;
  onSave: (note: string) => void;
  onCancel: () => void;
  onDelete?: () => void;
}) {
  const [note, setNote] = useState(initial);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSave(note);
      }}
      className="animate-enter space-y-2 rounded-lg border border-amber-400/60 bg-card p-3"
    >
      <label htmlFor="highlight-note" className="text-sm font-medium">
        {isNew ? "Note on this passage" : "Edit note"}
      </label>
      <textarea
        id="highlight-note"
        autoFocus
        rows={3}
        value={note}
        maxLength={5000}
        onChange={(e) => setNote(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onSave(note);
          if (e.key === "Escape") onCancel();
        }}
        placeholder="Why it matters, what it reminds you of…"
        className="block w-full resize-none rounded-md border bg-background px-2 py-1.5 text-sm outline-none focus:border-brand/60"
      />
      <div className="flex items-center gap-1">
        <Button type="submit" size="sm" className="bg-brand text-brand-foreground hover:bg-brand/85">
          Save
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        {onDelete && (
          <Button type="button" size="sm" variant="ghost" className="ml-auto text-muted-foreground" onClick={onDelete} aria-label="Remove highlight">
            <Trash2 />
          </Button>
        )}
      </div>
    </form>
  );
}
