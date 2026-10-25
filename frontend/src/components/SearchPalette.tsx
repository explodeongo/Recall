"use client";

import { useQuery } from "@tanstack/react-query";
import { FileText, Globe, Hash, Highlighter, MessageSquareText, NotebookPen, Plus, Sparkles } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { api, passageHref } from "@/lib/api";

const OPEN_EVENT = "recall:search";

/** Opens the search box from anywhere (the nav button uses this). */
export function openSearch() {
  window.dispatchEvent(new Event(OPEN_EVENT));
}

function useDebounced<T>(value: T, ms: number) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

/** ⌘K / Ctrl+K: jump to any document, passage, highlight, chat or tag, or ask a question. */
export function SearchPalette() {
  const router = useRouter();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const q = useDebounced(query.trim(), 150);
  const signedOut = pathname === "/login" || pathname === "/signup";

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_EVENT, onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_EVENT, onOpen);
    };
  }, []);

  const results = useQuery({
    queryKey: ["search", q],
    queryFn: () => api.search(q),
    enabled: open && q.length > 0 && !signedOut,
    placeholderData: (previous) => previous,
    staleTime: 10_000,
  });

  const go = (href: string) => {
    setOpen(false);
    setQuery("");
    router.push(href);
  };

  if (signedOut) return null;
  const r = q ? results.data : undefined;
  const nothing = r && !r.items.length && !r.passages.length && !r.highlights.length && !r.chats.length && !r.tags.length;

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title="Search your library" description="Search documents, passages, highlights and chats">
      {/* Results come from the server, so the list mustn't filter them a second time. */}
      <Command shouldFilter={false}>
        <CommandInput value={query} onValueChange={setQuery} placeholder="Search your library, or type a question…" />
        <CommandList className="max-h-[min(28rem,60vh)]">
          {q && (
            <CommandGroup>
              <CommandItem value={`ask ${q}`} onSelect={() => go(`/ask?q=${encodeURIComponent(q)}`)}>
                <Sparkles className="text-brand" />
                <span className="truncate">
                  Ask: <span className="font-medium">{q}</span>
                </span>
              </CommandItem>
            </CommandGroup>
          )}
          {!q && (
            <CommandGroup heading="Go to">
              <CommandItem value="new-chat" onSelect={() => go("/ask")}>
                <MessageSquareText /> New chat
              </CommandItem>
              <CommandItem value="add" onSelect={() => go("/add")}>
                <Plus /> Add to library
              </CommandItem>
              <CommandItem value="highlights" onSelect={() => go("/highlights")}>
                <Highlighter /> All highlights
              </CommandItem>
            </CommandGroup>
          )}
          {r && r.items.length > 0 && (
            <CommandGroup heading="Documents">
              {r.items.map((i) => (
                <CommandItem key={`i${i.id}`} value={`item-${i.id}`} onSelect={() => go(`/items/${i.id}`)}>
                  {i.source_type === "pdf" ? <FileText /> : <Globe />}
                  <span className="truncate">{i.title}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {r && r.passages.length > 0 && (
            <CommandGroup heading="Passages">
              {r.passages.map((p, n) => (
                <CommandItem
                  key={`p${p.item_id}-${n}`}
                  value={`passage-${p.item_id}-${n}`}
                  onSelect={() => go(passageHref({ item_id: p.item_id, chunk_id: 0, start_char: p.start_char, end_char: p.end_char, kind: p.kind }))}
                  className="items-start"
                >
                  {p.kind === "note" ? <NotebookPen className="mt-0.5" /> : <FileText className="mt-0.5" />}
                  <span className="min-w-0">
                    <span className="block truncate text-sm font-medium">
                      {p.kind === "note" ? `Your notes on ${p.title}` : p.title}
                      {p.page ? <span className="font-normal text-muted-foreground"> · p. {p.page}</span> : null}
                    </span>
                    <span className="line-clamp-2 text-xs text-muted-foreground">{p.text}</span>
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {r && r.highlights.length > 0 && (
            <CommandGroup heading="Your highlights">
              {r.highlights.map((h) => (
                <CommandItem
                  key={`h${h.id}`}
                  value={`highlight-${h.id}`}
                  onSelect={() => go(`/items/${h.item_id}?from=${h.start_char}&to=${h.end_char}`)}
                  className="items-start"
                >
                  <Highlighter className="mt-0.5" />
                  <span className="min-w-0">
                    <span className="line-clamp-2 text-sm">{h.quote}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {h.note ? `${h.note} · ` : ""}
                      {h.item_title}
                    </span>
                  </span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {r && r.chats.length > 0 && (
            <CommandGroup heading="Chats">
              {r.chats.map((c) => (
                <CommandItem key={`c${c.id}`} value={`chat-${c.id}`} onSelect={() => go(`/ask/${c.id}`)}>
                  <MessageSquareText />
                  <span className="truncate">{c.title}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {r && r.tags.length > 0 && (
            <CommandGroup heading="Tags">
              {r.tags.map((t) => (
                <CommandItem key={`t${t}`} value={`tag-${t}`} onSelect={() => go(`/?tag=${encodeURIComponent(t)}`)}>
                  <Hash />
                  {t}
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {nothing && <CommandEmpty>Nothing in your library matches. Try Ask instead.</CommandEmpty>}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
