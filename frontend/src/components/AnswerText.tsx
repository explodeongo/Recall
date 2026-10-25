"use client";

import Link from "next/link";
import { Fragment } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { Source } from "@/lib/api";
import { cn } from "@/lib/utils";

const CITATION = /\[(\d+(?:\s*,\s*\d+)*)\]/g;

/**
 * Renders an answer: paragraphs, "- " bullets and **bold**, with each [n] turned into a
 * numbered chip that previews the passage and opens it in the item it came from.
 */
export function AnswerText({ text, sources, streaming }: { text: string; sources: Source[]; streaming?: boolean }) {
  // The model is told to write plain text; unwrap any short inline LaTeX it uses anyway ($h = 8$).
  const blocks = toBlocks(text.replace(/\$([^$\n]{1,40})\$/g, "$1"));
  return (
    <div className={cn("space-y-3 font-heading text-[19px] leading-relaxed", streaming && "streaming")}>
      {blocks.map((block, i) =>
        block.kind === "list" ? (
          <ul key={i} className="list-disc space-y-1.5 pl-6 marker:text-muted-foreground">
            {block.lines.map((line, j) => (
              <li key={j}>
                <Inline text={line} sources={sources} />
              </li>
            ))}
          </ul>
        ) : (
          <p key={i}>
            <Inline text={block.lines.join(" ")} sources={sources} />
          </p>
        ),
      )}
    </div>
  );
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

function Inline({ text, sources }: { text: string; sources: Source[] }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(CITATION)) {
    parts.push(<Bold key={`t${last}`} text={text.slice(last, match.index)} />);
    const nums = match[1].split(",").map((n) => Number(n.trim()));
    parts.push(
      <span key={`c${match.index}`} className="whitespace-nowrap">
        {nums.map((n) => (
          <Citation key={n} source={sources[n - 1]} n={n} />
        ))}
      </span>,
    );
    last = match.index + match[0].length;
  }
  parts.push(<Bold key={`t${last}`} text={text.slice(last)} />);
  return <>{parts}</>;
}

function Bold({ text }: { text: string }) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
        part.startsWith("**") && part.endsWith("**") ? (
          <strong key={i} className="font-semibold">
            {part.slice(2, -2)}
          </strong>
        ) : (
          <Fragment key={i}>{part}</Fragment>
        ),
      )}
    </>
  );
}

function Citation({ source, n }: { source: Source | undefined; n: number }) {
  if (!source) return null; // a number the model made up; the server strips these too
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Link
            href={`/items/${source.item_id}?chunk=${source.chunk_id}`}
            className="mx-0.5 inline-grid h-[1.15rem] animate-pop min-w-[1.15rem] -translate-y-0.5 place-items-center rounded-md bg-brand-soft px-1 align-middle font-sans text-[11px] font-semibold text-brand tabular-nums no-underline transition-colors duration-150 hover:bg-brand hover:text-brand-foreground"
            aria-label={`Source ${n}: ${source.title}${source.page ? `, page ${source.page}` : ""}`}
          />
        }
      >
        {n}
      </TooltipTrigger>
      <TooltipContent className="block max-w-sm p-3 text-left">
        <span className="block font-medium">
          {source.title}
          {source.page ? ` · p. ${source.page}` : ""}
        </span>
        <span className="mt-1 line-clamp-5 opacity-80">{source.text}</span>
      </TooltipContent>
    </Tooltip>
  );
}
