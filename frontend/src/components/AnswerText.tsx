"use client";

import Link from "next/link";
import { Fragment } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { passageHref, siteOf, sourceName, type Source } from "@/lib/api";
import { cn } from "@/lib/utils";

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

/** The source numbers an answer cites, in the order it first uses them. */
export function citedInOrder(text: string, count: number): number[] {
  const seen: number[] = [];
  for (const match of text.matchAll(CITATION))
    for (const n of match[1].split(",").map((x) => Number(x.trim())))
      if (n >= 1 && n <= count && !seen.includes(n)) seen.push(n);
  return seen;
}

/**
 * What each source is called on screen. The model cites passages by search rank, which reads
 * as [2][3] with no [1]; shown, the cited ones are 1, 2, 3… in the order the answer uses them,
 * and the passages it didn't cite follow.
 */
export function displayNumbers(sources: Source[], cited: number[]): Map<number, number> {
  const order = [...cited, ...sources.map((s) => s.n).filter((n) => !cited.includes(n))];
  return new Map(order.map((n, i) => [n, i + 1]));
}

/** The answer text with its [n] markers in the numbers it's shown with. */
export function renumber(text: string, numbers: Map<number, number>): string {
  return text.replace(CITATION, (_, group: string) => `[${group.split(",").map((x) => numbers.get(Number(x.trim())) ?? x.trim()).join(", ")}]`);
}

/**
 * Renders an answer: paragraphs, "- " bullets and **bold**, with each [n] turned into a
 * numbered chip that previews the passage and opens it in the item it came from.
 */
export function AnswerText({ text, sources, streaming }: { text: string; sources: Source[]; streaming?: boolean }) {
  // The model is told to write plain text, but papers bring their maths along: unwrap
  // inline LaTeX ($h = 8$) and turn the common commands into the symbols they stand for.
  const blocks = toBlocks(plainMath(text.replace(/\$([^$\n]{1,60})\$/g, "$1")));
  const numbers = displayNumbers(sources, citedInOrder(text, sources.length));
  return (
    <div className={cn("space-y-3 font-heading text-[19px] leading-relaxed", streaming && "streaming")}>
      {blocks.map((block, i) =>
        block.kind === "list" ? (
          <ul key={i} className="list-disc space-y-1.5 pl-6 marker:text-muted-foreground">
            {block.lines.map((line, j) => (
              <li key={j}>
                <Inline text={line} sources={sources} numbers={numbers} />
              </li>
            ))}
          </ul>
        ) : (
          <p key={i}>
            <Inline text={block.lines.join(" ")} sources={sources} numbers={numbers} />
          </p>
        ),
      )}
    </div>
  );
}

const SYMBOLS: Record<string, string> = {
  alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ε", varepsilon: "ε", theta: "θ", lambda: "λ",
  mu: "μ", pi: "π", rho: "ρ", sigma: "σ", tau: "τ", phi: "φ", omega: "ω", Delta: "Δ", Sigma: "Σ", Omega: "Ω",
  cdot: "·", times: "×", div: "÷", pm: "±", leq: "≤", le: "≤", geq: "≥", ge: "≥", neq: "≠", ne: "≠", approx: "≈",
  infty: "∞", to: "→", rightarrow: "→", leftarrow: "←", Rightarrow: "⇒", in: "∈", sum: "Σ", prod: "∏",
  sqrt: "√", ldots: "…", dots: "…", cdots: "⋯", partial: "∂", nabla: "∇", circ: "∘",
  log: "log", ln: "ln", exp: "exp", sin: "sin", cos: "cos", max: "max", min: "min", softmax: "softmax",
};

/** Common LaTeX as readable text: \pi → π, \frac{a}{b} → a/b, \text{x} → x. Sub- and
 * superscripts (x_{i}, x^{2}) are left for <Bold> to render. */
export function plainMath(text: string) {
  if (!text.includes("\\")) return text;
  return text
    .replace(/\\sqrt\{([^{}]{1,30})\}/g, "√$1")
    .replace(/\\frac\{([^{}]{1,30})\}\{([^{}]{1,30})\}/g, "$1/$2")
    .replace(/\\(?:text|mathrm|mathbf|mathit|operatorname)\{([^{}]{1,40})\}/g, "$1")
    .replace(/\\([A-Za-z]+)/g, (whole, name: string) => SYMBOLS[name] ?? whole)
    .replace(/\\[,;! ]/g, " ");
}

type Block = { kind: "para" | "list"; lines: string[] };

function toBlocks(text: string): Block[] {
  const blocks: Block[] = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) {
      blocks.push({ kind: "para", lines: [] });
      continue;
    }
    const bullet = /^[-*•]\s+(.*)$/.exec(line);
    const kind = bullet ? "list" : "para";
    const last = blocks[blocks.length - 1];
    if (last && last.kind === kind && (kind === "list" || last.lines.length)) last.lines.push(bullet ? bullet[1] : line);
    else blocks.push({ kind, lines: [bullet ? bullet[1] : line] });
  }
  return blocks.filter((b) => b.lines.length);
}

function Inline({ text, sources, numbers }: { text: string; sources: Source[]; numbers: Map<number, number> }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    parts.push(<Bold key={`t${last}`} text={text.slice(last, match.index)} />);
    const nums = match[1].split(",").map((n) => Number(n.trim()));
    parts.push(
      <span key={`c${match.index}`} className="whitespace-nowrap">
        {nums.map((n) => (
          <Citation key={n} source={sources[n - 1]} n={numbers.get(n) ?? n} />
        ))}
      </span>,
    );
    last = match.index + match[0].length;
  }
  parts.push(<Bold key={`t${last}`} text={text.slice(last)} />);
  return <>{parts}</>;
}

/** **bold**, and maths sub- and superscripts: d_{model}, 10^{4}, x^2. */
function Bold({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*|[_^]\{[^{}]{1,24}\}|(?<=[A-Za-z0-9)])\^-?\d{1,3}\b)/g).map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i} className="font-semibold">
            {part.slice(2, -2)}
          </strong>
        ) : /^[_^]\{/.test(part) ? (
          part[0] === "_" ? (
            <sub key={i} className="text-[0.72em]">{part.slice(2, -1)}</sub>
          ) : (
            <sup key={i} className="text-[0.72em]">{part.slice(2, -1)}</sup>
          )
        ) : /^\^-?\d/.test(part) ? (
          <sup key={i} className="text-[0.72em]">{part.slice(1)}</sup>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

function Citation({ source, n }: { source: Source | undefined; n: number }) {
  if (!source) return null; // a number the model made up; the server strips these too
  const web = source.kind === "web";
  const chip = cn(
    // 20px chips, with a 32px hit area on touch screens.
    "relative mx-0.5 inline-grid h-5 animate-pop min-w-5 -translate-y-0.5 place-items-center rounded-md px-1 align-middle pointer-coarse:after:absolute pointer-coarse:after:-inset-1.5 font-sans text-[11px] font-semibold text-brand tabular-nums no-underline transition-colors duration-150 hover:bg-brand hover:text-brand-foreground",
    // Web sources look different from library ones: an outline instead of a fill.
    web ? "border border-brand/40" : "bg-brand-soft",
  );
  const label = `Source ${n}: ${sourceName(source)}${web ? `, ${siteOf(source.source)}` : source.page ? `, page ${source.page}` : ""}`;
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          web ? (
            <a href={source.source} target="_blank" rel="noreferrer" className={chip} aria-label={label} />
          ) : (
            <Link href={passageHref(source)} className={chip} aria-label={label} />
          )
        }
      >
        {n}
      </TooltipTrigger>
      <TooltipContent className="block max-w-sm p-3 text-left">
        <span className="block font-medium">
          {sourceName(source)}
          {web ? ` · ${siteOf(source.source)}` : source.page ? ` · p. ${source.page}` : ""}
        </span>
        <span className="mt-1 line-clamp-5 opacity-80">{source.text}</span>
      </TooltipContent>
    </Tooltip>
  );
}
