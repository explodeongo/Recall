"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Plus, Search, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { timeAgo } from "@/components/ItemBits";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type ChatSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Saved chats, newest first, with a "New chat" button and a search through everything said. */
export function ChatList({ activeId, onNavigate }: { activeId: number | null; onNavigate?: () => void }) {
  const [query, setQuery] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(query.trim()), 200);
    return () => clearTimeout(t);
  }, [query]);
  const all = useQuery({ queryKey: ["chats"], queryFn: () => api.chats() });
  const found = useQuery({ queryKey: ["chats", q], queryFn: () => api.chats(q), enabled: !!q, placeholderData: (previous) => previous });
  const chats = q ? found : all;
  // The box is for finding things in a long history; a short one is easier to scan.
  const searchable = (all.data?.filter((c) => c.message_count > 0).length ?? 0) > 4;

  return (
    <nav aria-label="Saved chats" className="flex flex-col gap-3">
      <Link href="/ask" onClick={onNavigate} className={cn(buttonVariants({ variant: "outline" }), "justify-start")}>
        <Plus /> New chat
      </Link>
      {searchable && (
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Escape" && setQuery("")}
            placeholder="Search chats"
            aria-label="Search chats"
            className="h-8 w-full rounded-md border bg-transparent pr-7 pl-8 text-sm outline-none transition-colors focus:border-brand/60 [&::-webkit-search-cancel-button]:hidden"
          />
          {query && (
            <button type="button" onClick={() => setQuery("")} aria-label="Clear search" className="absolute top-1/2 right-1.5 grid size-5 -translate-y-1/2 place-items-center rounded text-muted-foreground hover:bg-muted hover:text-foreground">
              <X className="size-3.5" />
            </button>
          )}
        </div>
      )}
      {chats.isPending ? (
        <div className="space-y-2 px-1" aria-busy="true">
          <Skeleton className="h-4 w-4/5" />
          <Skeleton className="h-4 w-3/5" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ) : chats.isError ? (
        <p className="px-1 text-sm text-muted-foreground">Couldn&apos;t load your chats.</p>
      ) : chats.data.filter((c) => c.message_count > 0 || c.id === activeId).length === 0 ? (
        <p className="px-1 text-sm text-muted-foreground">
          {q ? `No chat mentions “${q}”.` : "Your chats are saved here, so you can pick up where you left off."}
        </p>
      ) : (
        <ul className="-mx-1 space-y-0.5">
          {chats.data
            .filter((c) => c.message_count > 0 || c.id === activeId)
            .map((chat) => (
              <ChatRow key={chat.id} chat={chat} active={chat.id === activeId} onNavigate={onNavigate} />
            ))}
        </ul>
      )}
    </nav>
  );
}

function ChatRow({ chat, active, onNavigate }: { chat: ChatSummary; active: boolean; onNavigate?: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.deleteChat(chat.id),
    onSuccess: () => {
      queryClient.setQueryData<ChatSummary[]>(["chats"], (all) => all?.filter((c) => c.id !== chat.id));
      queryClient.removeQueries({ queryKey: ["chat", chat.id] });
      queryClient.invalidateQueries({ queryKey: ["chats"] });
      if (active) router.push("/ask");
    },
    onError: (err) => toast.error(err.message),
  });

  if (confirming) {
    return (
      <li className="flex items-center gap-2 rounded-md bg-destructive/5 px-2 py-1.5 text-sm">
        <span className="min-w-0 flex-1 truncate">Delete this chat?</span>
        <button onClick={() => remove.mutate()} disabled={remove.isPending} className="rounded px-1.5 py-0.5 font-medium text-destructive hover:bg-destructive/10">
          Delete
        </button>
        <button onClick={() => setConfirming(false)} autoFocus className="rounded px-1.5 py-0.5 text-muted-foreground hover:bg-muted">
          Cancel
        </button>
      </li>
    );
  }

  return (
    <li className="group/row relative">
      <Link
        href={`/ask/${chat.id}`}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        className={cn(
          "block rounded-md py-1.5 pr-8 pl-2 transition-colors duration-150",
          active ? "bg-muted text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
        )}
      >
        <span className="line-clamp-2 text-sm break-words">{chat.title}</span>
        {chat.match && <span className="mt-0.5 line-clamp-2 text-xs break-words text-muted-foreground italic">{chat.match}</span>}
        <span className="flex items-center gap-1 truncate text-xs text-muted-foreground">
          {chat.item_title && (
            <>
              <FileText className="size-3 shrink-0" aria-hidden />
              <span className="truncate">{chat.item_title}</span>
              <span aria-hidden>·</span>
            </>
          )}
          <span className="shrink-0">{timeAgo(chat.updated_at)}</span>
        </span>
      </Link>
      <button
        onClick={() => setConfirming(true)}
        aria-label={`Delete chat "${chat.title}"`}
        className="absolute top-1.5 right-1 rounded p-1 text-muted-foreground opacity-0 transition-opacity duration-150 group-hover/row:opacity-100 pointer-coarse:opacity-100 hover:bg-background hover:text-foreground focus-visible:opacity-100"
      >
        <Trash2 className="size-3.5" />
      </button>
    </li>
  );
}
