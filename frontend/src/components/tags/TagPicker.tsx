"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Settings2, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { tagStyle } from "@/components/ItemBits";
import { cleanTag, useTagManager } from "@/components/tags/TagManager";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api, type Item, type Tag } from "@/lib/api";

const MAX_TAGS = 12;
const NEW_TAG_COLOR = "#8d8d86"; // until the server gives the new tag its own

/** Sets an item's tags, showing the change at once wherever the item appears. */
export function useSetItemTags(item: Item) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (names: string[]) => api.setTags(item.id, names),
    onMutate: async (names) => {
      await queryClient.cancelQueries({ queryKey: ["items"] });
      const known = new Map(queryClient.getQueryData<Tag[]>(["tags"])?.map((t) => [t.name, t]));
      const tags = names.map((name, i) => known.get(name) ?? { id: -i - 1, name, color: NEW_TAG_COLOR });
      const patch = (old?: Item) => old && { ...old, tags };
      const previousItem = queryClient.getQueryData<Item>(["item", item.id]);
      const previousLists = queryClient.getQueriesData<Item[]>({ queryKey: ["items"] });
      queryClient.setQueryData<Item>(["item", item.id], patch);
      queryClient.setQueriesData<Item[]>({ queryKey: ["items"] }, (list) => list?.map((i) => (i.id === item.id ? patch(i)! : i)));
      return { previousItem, previousLists };
    },
    onError: (err, _names, context) => {
      queryClient.setQueryData(["item", item.id], context?.previousItem);
      context?.previousLists.forEach(([key, data]) => queryClient.setQueryData(key, data));
      toast.error(err.message);
    },
    onSuccess: (updated) => queryClient.setQueryData(["item", item.id], updated),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
      queryClient.invalidateQueries({ queryKey: ["tags"] });
    },
  });
}

/** Add or remove an item's tags from a searchable list, or make a new one by typing it. */
export function TagPicker({ item, trigger }: { item: Item; trigger: React.ReactElement }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const openManager = useTagManager();
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags, enabled: open });
  const save = useSetItemTags(item);
  const applied = item.tags.map((t) => t.name);
  const clean = cleanTag(query);
  const canCreate = !!clean && !tags.data?.some((t) => t.name === clean);

  function toggle(name: string) {
    if (applied.includes(name)) return save.mutate(applied.filter((n) => n !== name));
    if (applied.length >= MAX_TAGS) return toast.error(`An item can have up to ${MAX_TAGS} tags.`);
    save.mutate([...applied, name]);
  }

  // Tags already on the item first, so they're easy to take off.
  const sorted = [...(tags.data ?? [])].sort((a, b) => Number(applied.includes(b.name)) - Number(applied.includes(a.name)));

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setQuery("");
      }}
    >
      <PopoverTrigger render={trigger} />
      <PopoverContent className="w-64 p-0" align="start">
        <Command loop className="rounded-xl!">
          <CommandInput value={query} onValueChange={setQuery} placeholder="Find or make a tag…" aria-label="Find or make a tag" />
          <CommandList className="max-h-64">
            {!canCreate && <CommandEmpty className="py-4 text-xs text-muted-foreground">{tags.isPending ? "Loading…" : "No tags match."}</CommandEmpty>}
            {canCreate && (
              // Its own group: cmdk hides a group whose items don't match, forceMount or not.
              <CommandGroup forceMount className="pb-0">
                <CommandItem
                  forceMount
                  value={`__create ${clean}`}
                  onSelect={() => {
                    toggle(clean);
                    setQuery("");
                  }}
                >
                  <Plus className="text-muted-foreground" />
                  <span className="truncate">
                    Make <span className="font-medium">#{clean}</span>
                  </span>
                </CommandItem>
              </CommandGroup>
            )}
            <CommandGroup>
              {sorted.map((t) => (
                <CommandItem key={t.id} value={t.name} data-checked={applied.includes(t.name)} onSelect={() => toggle(t.name)}>
                  <span className="size-2.5 shrink-0 rounded-full" style={{ background: t.color }} aria-hidden />
                  <span className="truncate">#{t.name}</span>
                  <span className="ml-auto text-xs text-muted-foreground tabular-nums">{t.item_count}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              openManager();
            }}
            className="flex items-center gap-2 border-t px-3 py-2 text-left text-xs text-muted-foreground transition-colors duration-150 hover:bg-muted hover:text-foreground"
          >
            <Settings2 className="size-3.5" aria-hidden /> Colors, renaming and more…
          </button>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

/** An item's tags as removable colored chips. With a mouse, the × appears on hover or focus,
 * so it isn't hit on the way to the tag's link; on touch screens it's always there, and bigger. */
export function TagChip({ tag, href, onRemove }: { tag: Pick<Tag, "name" | "color">; href: string; onRemove?: () => void }) {
  return (
    <span style={tagStyle(tag.color)} className="group/chip tag-chip inline-flex animate-pop items-center rounded-full border text-xs">
      <Link href={href} className="py-0.5 pr-1 pl-2.5 hover:underline">
        #{tag.name}
      </Link>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove tag ${tag.name}`}
          className="mr-0.5 grid size-5 place-items-center rounded-full opacity-70 transition-opacity hover:bg-foreground/10 hover:opacity-100 pointer-fine:opacity-0 pointer-fine:group-hover/chip:opacity-70 pointer-fine:group-focus-within/chip:opacity-70 pointer-fine:hover:opacity-100 pointer-fine:focus-visible:opacity-100 pointer-coarse:size-6"
        >
          <X className="size-3" />
        </button>
      )}
    </span>
  );
}
