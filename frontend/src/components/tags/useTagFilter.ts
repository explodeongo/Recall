"use client";

import { useSearchParams } from "next/navigation";
import type { TagMatch } from "@/lib/api";

/** The Library's tag filter, kept in the URL: `?tags=a,b`, plus `&match=any` to show items
 * with any of them instead of all. The older one-tag `?tag=a` still works. */
export function useTagFilter() {
  const params = useSearchParams();
  const raw = [...(params.get("tags") ?? "").split(","), params.get("tag") ?? ""];
  const selected = [...new Set(raw.map((n) => n.trim().toLowerCase()).filter(Boolean))];
  const match: TagMatch = params.get("match") === "any" ? "any" : "all";

  function hrefWith(tags: string[], nextMatch: TagMatch = match) {
    const next = new URLSearchParams(params.toString());
    next.delete("tag");
    if (tags.length) next.set("tags", tags.join(","));
    else next.delete("tags");
    if (tags.length > 1 && nextMatch === "any") next.set("match", "any");
    else next.delete("match");
    return next.size ? `/?${next.toString().replaceAll("%2C", ",")}` : "/";
  }

  return {
    selected,
    match,
    hrefWith,
    /** The URL with `name` added to the filter, or taken out if it's already in it. */
    toggleHref: (name: string) => hrefWith(selected.includes(name) ? selected.filter((n) => n !== name) : [...selected, name]),
  };
}

/** "#a", "#a and #b", "#a, #b or #c". */
export function tagList(names: string[], match: TagMatch) {
  const tags = names.map((n) => `#${n}`);
  if (tags.length < 2) return tags.join("");
  return `${tags.slice(0, -1).join(", ")} ${match === "any" ? "or" : "and"} ${tags.at(-1)}`;
}
