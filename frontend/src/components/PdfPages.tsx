"use client";

import { Loader2, Maximize2, Minus, Plus } from "lucide-react";
import type { PDFDocumentProxy, PDFPageProxy, RenderTask, TextLayer } from "pdfjs-dist";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Zoom is relative to the panel's width: 1 fits a page across it.
const ZOOMS = [0.5, 0.67, 0.8, 0.9, 1, 1.25, 1.5, 2, 3];
// Pages are drawn when they come within this distance of the visible part, and dropped again
// past it: a drawn page holds a canvas of 10 to 20 MB, so a long PDF can't keep them all.
const NEAR = "150% 0px";
const GAP = 16;

type PdfJs = typeof import("pdfjs-dist");
let pdfjs: Promise<PdfJs> | null = null;

/** PDF.js loads only when a PDF is first opened here: it is about a megabyte. */
function loadPdfJs() {
  pdfjs ??= import("pdfjs-dist").then((lib) => {
    lib.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
    return lib;
  });
  return pdfjs;
}

/**
 * The PDF's own pages, drawn in the browser: a page counter, zoom, and text that can be
 * selected and copied. Pages are drawn as they scroll near, so long documents open at once.
 */
export function PdfPages({ url, startPage, onUnavailable }: { url: string; startPage?: number | null; onUnavailable?: () => void }) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  // Every page is laid out at the first page's shape until it is drawn: almost all PDFs use one size.
  const [shape, setShape] = useState(1.294);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [width, setWidth] = useState(0);
  const [current, setCurrent] = useState(startPage ?? 1);
  const [pageInput, setPageInput] = useState(String(startPage ?? 1));
  const scroller = useRef<HTMLDivElement>(null);
  const pages = useRef<(HTMLDivElement | null)[]>([]);
  const textLayer = useRef<typeof TextLayer | null>(null);
  const unavailable = useRef(onUnavailable);
  unavailable.current = onUnavailable;

  useEffect(() => {
    let cancelled = false;
    let loaded: PDFDocumentProxy | null = null;
    (async () => {
      try {
        const res = await fetch(url, { credentials: "include" });
        if (!res.ok) throw new Error(res.status === 404 ? "missing" : `The PDF didn't load (${res.status}).`);
        const [lib, data] = await Promise.all([loadPdfJs(), res.arrayBuffer()]);
        textLayer.current = lib.TextLayer;
        loaded = await lib.getDocument({ data }).promise;
        const first = await loaded.getPage(1);
        const view = first.getViewport({ scale: 1 });
        if (cancelled) return;
        setShape(view.height / view.width);
        setDoc(loaded);
      } catch (err) {
        if (cancelled) return;
        if (err instanceof Error && err.message === "missing") {
          setError("Recall doesn't have this PDF's file, only its text.");
          unavailable.current?.();
        } else {
          setError(err instanceof Error && err.message.startsWith("The PDF") ? err.message : "This PDF couldn't be shown.");
        }
      }
    })();
    return () => {
      cancelled = true;
      loaded?.destroy();
    };
  }, [url]);

  // The panel's inner width, which "fit width" fills.
  useEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)));
    observer.observe(el);
    return () => observer.disconnect();
  }, [doc]);

  const pageWidth = Math.max(0, Math.round((width - 2 * GAP) * zoom));

  const goTo = useCallback((n: number, smooth = true) => {
    const el = pages.current[n - 1];
    const box = scroller.current;
    if (!el || !box) return;
    const top = el.offsetTop - GAP;
    // Glide to a nearby page; jump to a far one, rather than scroll past every page between.
    const near = Math.abs(top - box.scrollTop) < box.clientHeight * 2;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    box.scrollTo({ top, behavior: smooth && near && !reduce ? "smooth" : "auto" });
  }, []);

  // Open at the requested page once the pages have their size.
  const opened = useRef(false);
  useEffect(() => {
    if (opened.current || !doc || !pageWidth) return;
    opened.current = true;
    if (startPage && startPage > 1) goTo(Math.min(startPage, doc.numPages), false);
  }, [doc, pageWidth, startPage, goTo]);

  // Keep the reader on the same page when zooming, rather than wherever that offset now lands.
  const zoomTo = (next: number) => {
    const page = current;
    setZoom(next);
    requestAnimationFrame(() => goTo(page, false));
  };

  // The page counter follows whichever page fills the middle of the panel.
  const onScroll = () => {
    const box = scroller.current;
    if (!box || !doc) return;
    const middle = box.scrollTop + box.clientHeight / 2;
    let n = 1;
    for (let i = 0; i < pages.current.length; i++) {
      const el = pages.current[i];
      if (el && el.offsetTop <= middle) n = i + 1;
      else break;
    }
    if (n !== current) {
      setCurrent(n);
      setPageInput(String(n));
    }
  };

  if (error) {
    return (
      <p role="alert" className="rounded-xl border bg-muted/40 p-5 text-sm text-muted-foreground">
        {error}
      </p>
    );
  }

  const step = (dir: 1 | -1) => {
    const i = ZOOMS.findIndex((z) => z >= zoom - 0.001);
    const next = ZOOMS[Math.min(ZOOMS.length - 1, Math.max(0, (ZOOMS[i] === zoom ? i : dir > 0 ? i - 1 : i) + dir))];
    zoomTo(next);
  };

  return (
    <div className="overflow-hidden rounded-xl border bg-muted/60">
      <div role="toolbar" aria-label="Page controls" className="flex items-center gap-1 border-b bg-card/80 px-2 py-1.5 text-sm">
        <form
          className="flex items-center gap-1.5 text-muted-foreground"
          onSubmit={(e) => {
            e.preventDefault();
            const n = Math.round(Number(pageInput));
            if (!doc || !Number.isFinite(n)) return setPageInput(String(current));
            const page = Math.min(doc.numPages, Math.max(1, n));
            setPageInput(String(page));
            setCurrent(page);
            goTo(page);
          }}
        >
          <label htmlFor="pdf-page" className="sr-only">
            Page
          </label>
          <input
            id="pdf-page"
            inputMode="numeric"
            value={pageInput}
            onChange={(e) => setPageInput(e.target.value.replace(/\D/g, ""))}
            onBlur={() => setPageInput(String(current))}
            // After the click that focused it, or the click would undo the selection.
            onFocus={(e) => {
              const input = e.target;
              requestAnimationFrame(() => input.select());
            }}
            disabled={!doc}
            className="h-7 w-10 rounded-md border bg-background text-center text-foreground tabular-nums outline-none focus-visible:ring-2 focus-visible:ring-ring/50 pointer-coarse:h-9"
          />
          <span className="tabular-nums">/ {doc ? doc.numPages : "…"}</span>
        </form>
        <div className="ml-auto flex items-center gap-0.5">
          <Button variant="ghost" size="icon-sm" className="pointer-coarse:size-10" aria-label="Zoom out" disabled={!doc || zoom <= ZOOMS[0]} onClick={() => step(-1)}>
            <Minus />
          </Button>
          <button
            type="button"
            onClick={() => zoomTo(1)}
            disabled={!doc}
            title="Fit to width"
            aria-label={`Zoom ${Math.round(zoom * 100)}%. Fit to width`}
            className="h-7 min-w-14 rounded-md px-1.5 pointer-coarse:h-10 text-muted-foreground tabular-nums transition-colors hover:bg-muted hover:text-foreground"
          >
            {Math.round(zoom * 100)}%
          </button>
          <Button variant="ghost" size="icon-sm" className="pointer-coarse:size-10" aria-label="Zoom in" disabled={!doc || zoom >= ZOOMS[ZOOMS.length - 1]} onClick={() => step(1)}>
            <Plus />
          </Button>
          <Button variant="ghost" size="icon-sm" className="pointer-coarse:size-10" aria-label="Fit to width" title="Fit to width" disabled={!doc || zoom === 1} onClick={() => zoomTo(1)}>
            <Maximize2 />
          </Button>
        </div>
      </div>
      <div
        ref={scroller}
        onScroll={onScroll}
        tabIndex={0}
        aria-label="PDF pages"
        className="relative max-h-[78dvh] overflow-auto overscroll-contain outline-none focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:ring-inset"
      >
        {!doc || !pageWidth ? (
          <div className="grid h-80 place-items-center text-sm text-muted-foreground" aria-busy="true">
            <span className="flex items-center gap-2">
              <Loader2 className="size-4 animate-spin" aria-hidden /> Opening the PDF…
            </span>
          </div>
        ) : (
          <div className="flex w-max min-w-full flex-col items-center" style={{ gap: GAP, padding: GAP }}>
            {Array.from({ length: doc.numPages }, (_, i) => (
              <PdfPage
                key={i}
                ref={(el) => {
                  pages.current[i] = el;
                }}
                doc={doc}
                number={i + 1}
                width={pageWidth}
                shape={shape}
                root={scroller}
                textLayer={textLayer.current!}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PdfPage({
  ref,
  doc,
  number,
  width,
  shape,
  root,
  textLayer: TextLayerClass,
}: {
  ref: (el: HTMLDivElement | null) => void;
  doc: PDFDocumentProxy;
  number: number;
  width: number;
  shape: number;
  root: React.RefObject<HTMLDivElement | null>;
  textLayer: typeof TextLayer;
}) {
  const box = useRef<HTMLDivElement | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const text = useRef<HTMLDivElement>(null);
  const [near, setNear] = useState(false);
  const [page, setPage] = useState<PDFPageProxy | null>(null);
  const [drawn, setDrawn] = useState(false);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const observer = new IntersectionObserver(([entry]) => setNear(entry.isIntersecting), { root: root.current, rootMargin: NEAR });
    observer.observe(el);
    return () => observer.disconnect();
  }, [root]);

  useEffect(() => {
    if (!near || page) return;
    let cancelled = false;
    doc.getPage(number).then((p) => !cancelled && setPage(p), () => {});
    return () => {
      cancelled = true;
    };
  }, [near, page, doc, number]);

  useEffect(() => {
    const c = canvas.current;
    const layer = text.current;
    if (!near || !page || !c || !layer || !width) return;
    const scale = width / page.getViewport({ scale: 1 }).width;
    const viewport = page.getViewport({ scale });
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    let task: RenderTask | null = null;
    let words: TextLayer | null = null;
    // Draw off screen, then swap in, so zooming doesn't flash a blank page.
    const next = document.createElement("canvas");
    next.width = Math.floor(viewport.width * ratio);
    next.height = Math.floor(viewport.height * ratio);
    task = page.render({ canvas: next, viewport, transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0] });
    task.promise.then(
      () => {
        c.width = next.width;
        c.height = next.height;
        c.getContext("2d")?.drawImage(next, 0, 0);
        next.width = next.height = 0;
        setDrawn(true);
      },
      () => {},
    );
    layer.replaceChildren();
    layer.style.setProperty("--total-scale-factor", String(scale));
    words = new TextLayerClass({ textContentSource: page.streamTextContent(), container: layer, viewport });
    words.render().catch(() => {});
    return () => {
      task?.cancel();
      words?.cancel();
    };
  }, [near, page, width, TextLayerClass]);

  // Out of range, give the memory back.
  useEffect(() => {
    if (near) return;
    const c = canvas.current;
    if (c) c.width = c.height = 0;
    text.current?.replaceChildren();
    setDrawn(false);
    page?.cleanup();
    setPage(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [near]);

  const view = page?.getViewport({ scale: 1 });
  const height = Math.round(width * (view ? view.height / view.width : shape));

  return (
    <div
      ref={(el) => {
        box.current = el;
        ref(el);
      }}
      role="group"
      aria-label={`Page ${number}`}
      className="pdf-page relative shrink-0 overflow-hidden rounded-[3px] bg-white shadow-md"
      style={{ width, height }}
    >
      <canvas ref={canvas} aria-hidden className={cn("absolute inset-0 size-full", !drawn && "invisible")} />
      <div ref={text} className="textLayer" />
      {!drawn && (
        <span className="absolute inset-0 grid place-items-center text-xs text-neutral-400 tabular-nums" aria-hidden>
          {number}
        </span>
      )}
    </div>
  );
}
