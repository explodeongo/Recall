"use client";

import { useQuery } from "@tanstack/react-query";
import { CircleDashed, ExternalLink, Loader2, MessageSquareText, Minus, Plus, RotateCw, Scan, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { SourceIcon, sourceLabel, tagStyle, timeAgo } from "@/components/ItemBits";
import { Button, buttonVariants } from "@/components/ui/button";
import { api, passageHref, type Graph, type GraphCluster, type GraphNode } from "@/lib/api";
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
            Everything you&apos;ve saved, linked by topic. Items about the same things gather into groups, named after the tag they
            share. Click an item to see what it connects to.
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
        <div className="grid h-[60vh] place-items-center rounded-xl border bg-card shadow-xs" aria-busy="true">
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
    // A gentle pull to the middle keeps items from drifting off; weaker for unlinked ones,
    // so they settle around the edges instead of inside a group.
    const gravity = n.degree === 0 ? 0.0012 : 0.004;
    n.vx += (width / 2 - n.x) * gravity * alpha;
    n.vy += (height / 2 - n.y) * gravity * alpha;
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
  const [hover, setHover] = useState<number | null>(null);
  // The item whose panel is open; its links stay lit while nothing else is hovered.
  const [selected, setSelected] = useState<number | null>(focus);
  const [orphansOnly, setOrphansOnly] = useState(false);
  const clusterById = useMemo(() => new Map(data.clusters.map((c) => [c.id, c])), [data.clusters]);
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
    // Groups' halos and their names count too, so nothing is cut off at the edges.
    const xs = [...nodes.map((n) => n.x), ...halos.flatMap((h) => [h.cx - h.r, h.cx + h.r])];
    const ys = [...nodes.map((n) => n.y), ...halos.flatMap((h) => [h.cy - h.r - 22, h.cy + h.r])];
    const [minX, maxX, minY, maxY] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
    const k = Math.min(1.8, Math.max(0.3, Math.min((size.width - 120) / (maxX - minX || 1), (size.height - 80) / (maxY - minY || 1))));
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

  const active = hover ?? selected;
  const lit = (id: number) => {
    if (active !== null) return id === active || !!neighbours.get(active)?.has(id);
    if (orphansOnly) return !neighbours.has(id);
    if (tag) return nodes.find((n) => n.id === id)!.tags.some((t) => t.name === tag);
    return true;
  };
  const colorOf = (n: SimNode) => (n.cluster !== null ? clusterById.get(n.cluster)?.color : null) ?? n.tags[0]?.color ?? NEUTRAL;
  const orphans = nodes.filter((n) => n.degree === 0);

  // Each group's halo: around the middle of its items, wide enough to hold them all.
  const halos = data.clusters.map((c) => {
    const members = nodes.filter((n) => n.cluster === c.id);
    const cx = members.reduce((sum, n) => sum + n.x, 0) / members.length;
    const cy = members.reduce((sum, n) => sum + n.y, 0) / members.length;
    const r = Math.max(...members.map((n) => Math.hypot(n.x - cx, n.y - cy))) + 34;
    const on = active === null ? !orphansOnly : members.some((n) => n.id === active);
    return { cluster: c, cx, cy, r, on };
  });

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
      if (!d.moved) setSelected(d.node.id);
    } else if (d && !d.moved) {
      setSelected(null); // a click on empty space closes the panel
    }
  };

  // On wider screens the panel covers the right of the graph: bring the chosen item into
  // the part that's still visible.
  useEffect(() => {
    const node = nodes.find((n) => n.id === selected);
    if (!node || size.width < 640) return;
    const visible = size.width - 352;
    setView((v) => {
      const x = node.x * v.k + v.x;
      // Room for the item's name either side, not just its dot.
      return x > 120 && x < visible - 120 ? v : { ...v, x: visible / 2 - node.x * v.k };
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSelected(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
  const showLabel = (n: SimNode) => active === n.id || (active !== null && lit(n.id)) || view.k >= 1.4 || n.degree >= 3 || nodes.length <= 12;
  const hovered = hover !== selected ? nodes.find((n) => n.id === hover) : undefined;
  const chosen = nodes.find((n) => n.id === selected);

  return (
    <div ref={box} className="relative h-[68vh] min-h-96 overflow-hidden rounded-xl border bg-card shadow-xs">
      <svg
        ref={svg}
        width={size.width}
        height={size.height}
        className="cursor-grab touch-none select-none active:cursor-grabbing"
        onPointerDown={(e) => onPointerDown(e, null)}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={() => !drag.current && setHover(null)}
        role="group"
        aria-label={`Graph of ${nodes.length} items and ${links.length} links`}
      >
        <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
          {halos.map(({ cluster, cx, cy, r, on }) => (
            <g key={cluster.id} className="pointer-events-none transition-opacity duration-200" opacity={on ? 1 : 0.35}>
              <circle cx={cx} cy={cy} r={r} fill={cluster.color ?? "var(--foreground)"} fillOpacity={0.06} stroke={cluster.color ?? "var(--foreground)"} strokeOpacity={0.18} strokeWidth={1 / view.k} />
              <text
                x={cx}
                y={cy - r - 7 / view.k}
                textAnchor="middle"
                fontSize={12 / view.k}
                fontWeight={600}
                fill={cluster.color ?? "var(--muted-foreground)"}
                paintOrder="stroke"
                stroke="var(--card)"
                strokeWidth={3 / view.k}
              >
                {groupName(cluster)}
              </text>
            </g>
          ))}
          {links.map(([a, b, s]) => {
            const on = lit(a.id) && lit(b.id) && (active === null || a.id === active || b.id === active);
            return (
              <line
                key={`${a.id}-${b.id}`}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke="var(--foreground)"
                strokeOpacity={on ? 0.12 + (s - 0.5) * 0.9 : 0.04}
                strokeWidth={(on && active !== null ? 1.6 : 1) / view.k}
                className="transition-[stroke-opacity] duration-200"
              />
            );
          })}
          {nodes.map((n) => {
            const color = colorOf(n);
            const on = lit(n.id);
            const orphan = n.degree === 0;
            return (
              <a
                key={n.id}
                href={`/items/${n.id}`}
                aria-label={`${n.title}${n.tags.length ? `, tagged ${n.tags.map((t) => t.name).join(", ")}` : ""}, ${orphan ? "not linked yet" : `${n.degree} ${n.degree === 1 ? "link" : "links"}`}`}
                aria-current={selected === n.id ? "true" : undefined}
                onClick={(e) => e.preventDefault()}
                onDoubleClick={() => router.push(`/items/${n.id}`)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    setSelected(n.id);
                  }
                }}
                onFocus={() => setHover(n.id)}
                onBlur={() => setHover(null)}
                onPointerEnter={() => !drag.current && setHover(n.id)}
                onPointerLeave={() => !drag.current && setHover(null)}
                onPointerDown={(e) => onPointerDown(e, n)}
                className="cursor-pointer outline-none [&:focus-visible>circle]:stroke-(--brand)"
              >
                {selected === n.id && <circle cx={n.x} cy={n.y} r={radius(n) + 6} fill="none" stroke={color} strokeWidth={2 / view.k} className="animate-pop [transform-box:fill-box] origin-center" />}
                {/* Items linked to nothing are drawn hollow. */}
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={radius(n) + (active === n.id ? 2 : 0)}
                  fill={orphan ? "var(--card)" : color}
                  fillOpacity={on ? 1 : 0.18}
                  stroke={orphan ? color : "var(--card)"}
                  strokeOpacity={on ? 1 : 0.3}
                  strokeDasharray={orphan ? `${3 / view.k} ${2 / view.k}` : undefined}
                  strokeWidth={(orphan ? 1.6 : 2) / view.k}
                  className="transition-[fill-opacity,stroke-opacity,r] duration-200 ease-(--ease-out)"
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

      <div
        className={cn(
          "absolute top-3 right-3 flex flex-col gap-1 rounded-lg border bg-background/90 p-1 shadow-xs backdrop-blur transition-[right] duration-200 ease-(--ease-out)",
          chosen && "sm:right-[21.5rem]",
        )}
      >
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
          "pointer-events-none absolute top-3 left-3 max-w-xs rounded-lg border bg-background/95 px-3 py-2 text-sm shadow-sm backdrop-blur transition-[opacity,transform] duration-150 ease-(--ease-out)",
          hovered ? "opacity-100" : "-translate-y-1 opacity-0",
        )}
        aria-hidden
      >
        {hovered && (
          <>
            <p className="line-clamp-2 font-medium">{hovered.title}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {hovered.degree === 0 ? "Not linked yet" : `${hovered.degree} ${hovered.degree === 1 ? "connection" : "connections"}`}
              {hovered.tags.length > 0 && ` · ${hovered.tags.map((t) => `#${t.name}`).join(" ")}`}
            </p>
          </>
        )}
      </div>
      {orphans.length > 0 && (
        <button
          onClick={() => {
            setSelected(null);
            setOrphansOnly((v) => !v);
          }}
          aria-pressed={orphansOnly}
          className={cn(
            "absolute bottom-3 left-3 flex items-center gap-1.5 rounded-full border bg-background/90 px-3 py-1 text-xs shadow-xs backdrop-blur transition-[color,border-color,transform] duration-150 active:scale-[0.97]",
            orphansOnly ? "border-brand/50 text-brand" : "text-muted-foreground hover:text-foreground",
          )}
          title="Items that don't connect to anything else yet"
        >
          <CircleDashed className="size-3.5" aria-hidden />
          {orphans.length} not linked yet
        </button>
      )}
      {!chosen && (
        <p className="pointer-events-none absolute right-3 bottom-3 hidden text-xs text-muted-foreground sm:block">
          Click to see connections · double-click to open · drag · scroll to zoom
        </p>
      )}

      {chosen && (
        <NodePanel
          key={chosen.id}
          node={chosen}
          cluster={chosen.cluster !== null ? (clusterById.get(chosen.cluster) ?? null) : null}
          color={colorOf(chosen)}
          onSelect={(id) => setSelected(nodes.some((n) => n.id === id) ? id : null)}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}

function groupName(cluster: GraphCluster) {
  return cluster.label ? `#${cluster.label}` : `${cluster.size} related items`;
}

/** The selected item: what it is, its group, and what it connects to (with the passage). */
function NodePanel({
  node,
  cluster,
  color,
  onSelect,
  onClose,
}: {
  node: SimNode;
  cluster: GraphCluster | null;
  color: string;
  onSelect: (id: number) => void;
  onClose: () => void;
}) {
  const item = useQuery({ queryKey: ["item", node.id], queryFn: () => api.item(node.id) });
  const found = useQuery({ queryKey: ["connections", node.id], queryFn: () => api.connections(node.id), staleTime: 60_000 });

  return (
    <aside
      aria-label={`About ${node.title}`}
      className="absolute inset-x-0 bottom-0 flex max-h-[50%] animate-enter flex-col overflow-hidden rounded-t-2xl border-t bg-background shadow-lg sm:inset-y-0 sm:right-0 sm:left-auto sm:max-h-none sm:w-84 sm:rounded-none sm:border-t-0 sm:border-l"
    >
      <div className="flex items-start gap-2 border-b p-4">
        <span className="mt-2 size-2.5 shrink-0 rounded-full" style={{ background: color }} aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="font-heading text-lg leading-snug font-medium">{node.title}</h2>
          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
            <SourceIcon type={node.source_type} className="size-3.5" />
            {item.data ? `${sourceLabel(item.data)} · ` : ""}saved {timeAgo(node.created_at)}
          </p>
        </div>
        <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close">
          <X />
        </Button>
      </div>

      <div className="flex-1 space-y-5 overflow-y-auto p-4">
        {node.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {node.tags.map((t) => (
              <Link key={t.id} href={`/?tags=${encodeURIComponent(t.name)}`} style={tagStyle(t.color)} className="tag-chip rounded-full border px-2 py-0.5 text-xs">
                #{t.name}
              </Link>
            ))}
          </div>
        )}
        {item.data?.summary && <p className="text-sm leading-relaxed text-pretty">{item.data.summary}</p>}

        <div className="flex gap-2">
          <Link href={`/items/${node.id}`} className={buttonVariants({ size: "sm" })}>
            <ExternalLink /> Open
          </Link>
          <Link href={`/ask?item=${node.id}`} className={buttonVariants({ size: "sm", variant: "outline" })}>
            <MessageSquareText /> Ask about it
          </Link>
        </div>

        <section aria-labelledby="panel-links" className="space-y-2">
          <h3 id="panel-links" className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
            {cluster ? `In ${groupName(cluster)} · ${cluster.size} items` : node.degree === 0 ? "Not linked yet" : "Connections"}
          </h3>
          {node.degree === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nothing else you&apos;ve saved is close to this in topic yet. It links up once you save more on the same subject.
            </p>
          ) : found.isPending ? (
            <Loader2 className="size-4 animate-spin text-muted-foreground motion-reduce:animate-none" aria-label="Loading connections" />
          ) : (
            <ul className="space-y-2">
              {found.data?.map((c) => (
                <li key={c.item.id} className="rounded-lg border p-3">
                  <button onClick={() => onSelect(c.item.id)} className="text-left text-sm leading-snug font-medium hover:text-brand">
                    {c.item.title}
                  </button>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    {c.similarity >= 0.7 ? "Closely related" : "Related topic"}
                    {c.shared_tags.length > 0 && ` · shares ${c.shared_tags.map((t) => `#${t}`).join(" ")}`}
                  </p>
                  {c.passage && (
                    <Link
                      href={passageHref({ item_id: c.item.id, chunk_id: c.passage.chunk_id, start_char: c.passage.start_char, end_char: c.passage.end_char, kind: "text" })}
                      className="mt-2 line-clamp-3 rounded-md bg-muted/50 px-2 py-1.5 text-xs text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-foreground"
                    >
                      {c.passage.text}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </aside>
  );
}
