"use client";

import { useQuery } from "@tanstack/react-query";
import { Loader2, Minus, Plus, RotateCw, Scan } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { tagStyle } from "@/components/ItemBits";
import { Button, buttonVariants } from "@/components/ui/button";
import { api, type Graph, type GraphNode } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function GraphPage() {
  return (
    <Suspense fallback={null}>
      <GraphView />
    </Suspense>
  );
}

interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  degree: number;
  pinned: boolean;
}

const NEUTRAL = "#8d8d86";

function GraphView() {
  const params = useSearchParams();
  const focus = Number(params.get("focus")) || null;
  const graph = useQuery({ queryKey: ["graph"], queryFn: api.graph });
  const [tag, setTag] = useState<string | null>(null);

  const tags = useMemo(() => {
    const counts = new Map<string, { name: string; color: string; n: number }>();
    for (const node of graph.data?.nodes ?? [])
      for (const t of node.tags) counts.set(t.name, { ...t, n: (counts.get(t.name)?.n ?? 0) + 1 });
    return [...counts.values()].sort((a, b) => b.n - a.n).slice(0, 14);
  }, [graph.data]);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-balance font-heading text-4xl font-medium">Graph</h1>
          <p className="mt-1 max-w-prose text-sm text-muted-foreground">
            Everything you&apos;ve saved, linked by topic. Items that talk about the same things sit together; colors are their first tag.
          </p>
        </div>
      </header>

      {tags.length > 0 && (
        <nav aria-label="Highlight a tag" className="flex flex-wrap gap-1.5">
          {tags.map((t) => (
            <button
              key={t.name}
              onClick={() => setTag(tag === t.name ? null : t.name)}
              aria-pressed={tag === t.name}
              data-active={tag === t.name ? "" : undefined}
              style={tagStyle(t.color)}
              className="tag-chip inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs transition-[color,background-color,border-color,transform] duration-150 ease-(--ease-out) active:scale-[0.97]"
            >
              #{t.name} <span className="tabular-nums opacity-60">{t.n}</span>
            </button>
          ))}
        </nav>
      )}

      {graph.isPending ? (
        <div className="grid h-[60vh] place-items-center rounded-xl border bg-card" aria-busy="true">
          <Loader2 className="size-5 animate-spin text-muted-foreground motion-reduce:animate-none" aria-label="Loading the graph" />
        </div>
      ) : graph.isError ? (
        <div role="alert" className="flex items-center justify-between gap-4 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm">
          <span>{graph.error.message}</span>
          <Button variant="outline" size="sm" onClick={() => graph.refetch()}>
            <RotateCw /> Retry
          </Button>
        </div>
      ) : graph.data.nodes.length < 2 ? (
        <div className="rounded-xl border border-dashed p-8 text-center">
          <p className="font-medium">The graph appears once you&apos;ve saved a few things</p>
          <p className="mt-1 text-sm text-muted-foreground">Save two or more items and Recall links the ones on related topics.</p>
          <Link href="/add" className={buttonVariants({ variant: "outline", className: "mt-4" })}>
            <Plus /> Add item
          </Link>
        </div>
      ) : (
        <Canvas key={graph.dataUpdatedAt} data={graph.data} tag={tag} focus={focus} />
      )}
    </div>
  );
}

/** Lays the graph out with a small force simulation: items push apart, links pull together. */
function layout(data: Graph, width: number, height: number): { nodes: SimNode[]; links: [SimNode, SimNode, number][] } {
  const degree = new Map<number, number>();
  for (const e of data.edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }
  // Start on a spiral, so the result is the same on every load.
  const nodes: SimNode[] = data.nodes.map((n, i) => {
    const angle = i * 2.39996;
    const r = 14 * Math.sqrt(i + 1);
    return { ...n, x: width / 2 + r * Math.cos(angle), y: height / 2 + r * Math.sin(angle), vx: 0, vy: 0, degree: degree.get(n.id) ?? 0, pinned: false };
  });
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const links = data.edges.flatMap((e) => {
    const a = byId.get(e.source);
    const b = byId.get(e.target);
    return a && b ? [[a, b, e.similarity] as [SimNode, SimNode, number]] : [];
  });
  return { nodes, links };
}

function tick(nodes: SimNode[], links: [SimNode, SimNode, number][], width: number, height: number, alpha: number) {
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i];
    for (let j = i + 1; j < nodes.length; j++) {
      const b = nodes[j];
      let dx = b.x - a.x;
      let dy = b.y - a.y;
      let d2 = dx * dx + dy * dy;
      if (d2 < 0.01) {
        dx = Math.random() - 0.5;
        dy = Math.random() - 0.5;
        d2 = 0.5;
      }
      if (d2 > 250_000) continue;
      const force = (2400 * alpha) / d2;
      const d = Math.sqrt(d2);
      a.vx -= (dx / d) * force;
      a.vy -= (dy / d) * force;
      b.vx += (dx / d) * force;
      b.vy += (dy / d) * force;
    }
  }
  for (const [a, b, similarity] of links) {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const rest = 70 + (1 - similarity) * 160;
    const pull = ((d - rest) / d) * 0.06 * alpha;
    a.vx += dx * pull;
    a.vy += dy * pull;
    b.vx -= dx * pull;
    b.vy -= dy * pull;
  }
  for (const n of nodes) {
    // A gentle pull to the middle keeps unlinked items from drifting off.
    n.vx += (width / 2 - n.x) * 0.004 * alpha;
    n.vy += (height / 2 - n.y) * 0.004 * alpha;
    if (n.pinned) {
      n.vx = n.vy = 0;
      continue;
    }
    n.vx *= 0.82;
    n.vy *= 0.82;
    n.x += n.vx;
    n.y += n.vy;
  }
}

function Canvas({ data, tag, focus }: { data: Graph; tag: string | null; focus: number | null }) {
  const router = useRouter();
  const box = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({ width: 900, height: 600 });
  const [, setFrame] = useState(0);
  const [view, setView] = useState({ x: 0, y: 0, k: 1 });
  const [hover, setHover] = useState<number | null>(focus);
  const sim = useRef<ReturnType<typeof layout> | null>(null);
  const alpha = useRef(1);
  const raf = useRef(0);

  useEffect(() => {
    const el = box.current!;
    const observer = new ResizeObserver(([entry]) => setSize({ width: entry.contentRect.width, height: entry.contentRect.height }));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  if (sim.current === null) {
    sim.current = layout(data, size.width, size.height);
    // Settle most of the way before the first paint, so the graph arrives mostly still.
    for (let i = 0; i < 220; i++) tick(sim.current.nodes, sim.current.links, size.width, size.height, 1 - i / 260);
    alpha.current = 0.15;
  }

  const animate = () => {
    cancelAnimationFrame(raf.current);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const step = () => {
      const s = sim.current!;
      if (reduced) {
        for (let i = 0; i < 120; i++) tick(s.nodes, s.links, size.width, size.height, alpha.current);
        alpha.current = 0;
      } else {
        tick(s.nodes, s.links, size.width, size.height, alpha.current);
        alpha.current *= 0.97;
      }
      setFrame((f) => f + 1);
      if (alpha.current > 0.005) raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
  };

  useEffect(() => {
    animate();
    return () => cancelAnimationFrame(raf.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size.width, size.height]);

  const { nodes, links } = sim.current;

  // Frame the whole graph, with room for labels. Done on load and resize until the reader
  // pans or zooms themselves.
  const touched = useRef(false);
  const fit = () => {
    const xs = nodes.map((n) => n.x);
    const ys = nodes.map((n) => n.y);
    const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const k = Math.min(1.8, Math.max(0.3, Math.min((size.width - 200) / (maxX - minX || 1), (size.height - 140) / (maxY - minY || 1))));
    setView({ k, x: size.width / 2 - ((minX + maxX) / 2) * k, y: size.height / 2 - ((minY + maxY) / 2) * k });
  };
  useEffect(() => {
    if (!touched.current) fit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size.width, size.height]);
  const neighbours = useMemo(() => {
    const map = new Map<number, Set<number>>();
    for (const [a, b] of links) {
      map.set(a.id, (map.get(a.id) ?? new Set()).add(b.id));
      map.set(b.id, (map.get(b.id) ?? new Set()).add(a.id));
    }
    return map;
  }, [links]);

  const lit = (id: number) => {
    if (hover !== null) return id === hover || !!neighbours.get(hover)?.has(id);
    if (tag) return nodes.find((n) => n.id === id)!.tags.some((t) => t.name === tag);
    return true;
  };

  // Screen point to graph point.
  const toGraph = (clientX: number, clientY: number) => {
    const rect = svg.current!.getBoundingClientRect();
    return { x: (clientX - rect.left - view.x) / view.k, y: (clientY - rect.top - view.y) / view.k };
  };

  const drag = useRef<{ node: SimNode | null; startX: number; startY: number; viewX: number; viewY: number; moved: boolean } | null>(null);

  const onPointerDown = (e: React.PointerEvent, node: SimNode | null) => {
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    drag.current = { node, startX: e.clientX, startY: e.clientY, viewX: view.x, viewY: view.y, moved: false };
    if (node) {
      e.stopPropagation();
      node.pinned = true;
    }
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    if (Math.abs(e.clientX - d.startX) + Math.abs(e.clientY - d.startY) > 3) d.moved = true;
    if (d.node) {
      const p = toGraph(e.clientX, e.clientY);
      d.node.x = p.x;
      d.node.y = p.y;
      alpha.current = Math.max(alpha.current, 0.25);
      animate();
    } else {
      touched.current = true;
      setView((v) => ({ ...v, x: d.viewX + e.clientX - d.startX, y: d.viewY + e.clientY - d.startY }));
    }
  };
  const onPointerUp = () => {
    const d = drag.current;
    drag.current = null;
    if (d?.node) {
      d.node.pinned = false;
      if (!d.moved) router.push(`/items/${d.node.id}`);
    }
  };

  const zoomBy = (factor: number, cx = size.width / 2, cy = size.height / 2) => {
    touched.current = true;
    setView((v) => {
      const k = Math.min(4, Math.max(0.3, v.k * factor));
      return { k, x: cx - ((cx - v.x) * k) / v.k, y: cy - ((cy - v.y) * k) / v.k };
    });
  };

  useEffect(() => {
    const el = svg.current!;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      zoomBy(Math.exp(-e.deltaY * 0.0015), e.clientX - rect.left, e.clientY - rect.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [size.width, size.height]);


  const radius = (n: SimNode) => 5 + Math.sqrt(n.degree) * 2.2;
  const showLabel = (n: SimNode) => hover === n.id || (hover !== null && lit(n.id)) || view.k >= 1.4 || n.degree >= 3 || nodes.length <= 12;
  const hovered = nodes.find((n) => n.id === hover);

  return (
    <div ref={box} className="relative h-[68vh] min-h-96 overflow-hidden rounded-xl border bg-card">
      <svg
        ref={svg}
        width={size.width}
        height={size.height}
        className="cursor-grab touch-none select-none active:cursor-grabbing"
        onPointerDown={(e) => onPointerDown(e, null)}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => !drag.current && setHover(focus)}
        role="group"
        aria-label={`Graph of ${nodes.length} items and ${links.length} links`}
      >
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {links.map(([a, b, s]) => {
            const on = lit(a.id) && lit(b.id) && (hover === null || a.id === hover || b.id === hover);
            return (
              <line
                key={`${a.id}-${b.id}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="var(--foreground)"
                strokeOpacity={on ? 0.12 + (s - 0.5) * 0.9 : 0.04}
                strokeWidth={(on && hover !== null ? 1.6 : 1) / view.k}
                className="transition-[stroke-opacity] duration-200"
              />
            );
          })}
          {nodes.map((n) => {
            const color = n.tags[0]?.color ?? NEUTRAL;
            const on = lit(n.id);
            return (
              <a
                key={n.id}
                href={`/items/${n.id}`}
                aria-label={`${n.title}${n.tags.length ? `, tagged ${n.tags.map((t) => t.name).join(", ")}` : ""}, ${n.degree} ${n.degree === 1 ? "link" : "links"}`}
                onClick={(e) => e.preventDefault()}
                onKeyDown={(e) => e.key === "Enter" && router.push(`/items/${n.id}`)}
                onFocus={() => setHover(n.id)}
                onBlur={() => setHover(focus)}
                onPointerEnter={() => !drag.current && setHover(n.id)}
                onPointerLeave={() => !drag.current && setHover(focus)}
                onPointerDown={(e) => onPointerDown(e, n)}
                className="cursor-pointer outline-none [&:focus-visible>circle]:stroke-(--brand)"
              >
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={radius(n) + (hover === n.id ? 2 : 0)}
                  fill={color}
                  fillOpacity={on ? 1 : 0.18}
                  stroke="var(--card)"
                  strokeWidth={2 / view.k}
                  className="transition-[fill-opacity,r] duration-200 ease-(--ease-out)"
                />
                {showLabel(n) && (
                  <text
                    x={n.x}
                    y={n.y + radius(n) + 13 / view.k}
                    textAnchor="middle"
                    fontSize={12 / view.k}
                    fill="var(--foreground)"
                    fillOpacity={on ? 0.85 : 0.2}
                    paintOrder="stroke"
                    stroke="var(--card)"
                    strokeWidth={3 / view.k}
                    className="pointer-events-none"
                  >
                    {n.title.length > 34 ? n.title.slice(0, 33) + "…" : n.title}
                  </text>
                )}
              </a>
            );
          })}
        </g>
      </svg>

      <div className="absolute top-3 right-3 flex flex-col gap-1 rounded-lg border bg-background/90 p-1 shadow-xs backdrop-blur">
        <Button size="icon-sm" variant="ghost" onClick={() => zoomBy(1.25)} aria-label="Zoom in">
          <Plus />
        </Button>
        <Button size="icon-sm" variant="ghost" onClick={() => zoomBy(0.8)} aria-label="Zoom out">
          <Minus />
        </Button>
        <Button size="icon-sm" variant="ghost" onClick={fit} aria-label="Fit everything">
          <Scan />
        </Button>
      </div>

      <div
        className={cn(
          "pointer-events-none absolute bottom-3 left-3 max-w-xs rounded-lg border bg-background/95 px-3 py-2 text-sm shadow-sm backdrop-blur transition-[opacity,transform] duration-150 ease-(--ease-out)",
          hovered ? "opacity-100" : "translate-y-1 opacity-0",
        )}
        aria-hidden
      >
        {hovered && (
          <>
            <p className="line-clamp-2 font-medium">{hovered.title}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {hovered.degree} {hovered.degree === 1 ? "connection" : "connections"}
              {hovered.tags.length > 0 && ` · ${hovered.tags.map((t) => `#${t.name}`).join(" ")}`}
            </p>
          </>
        )}
      </div>
      <p className="pointer-events-none absolute right-3 bottom-3 hidden text-xs text-muted-foreground sm:block">Drag to move · scroll to zoom · click to open</p>
    </div>
  );
}
