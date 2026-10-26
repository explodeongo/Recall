"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { createContext, useContext, useState } from "react";
import { toast } from "sonner";
import { ColorWheel } from "@/components/tags/ColorWheel";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { api, type TagWithCount } from "@/lib/api";
import { PRESET_COLORS } from "@/lib/color";

/** Same rules as the server's clean_tag: lowercase letters, numbers, spaces and - . + # */
export function cleanTag(raw: string) {
  const name = raw
    .toLowerCase()
    .replace(/[^a-z0-9+#.\- ]/g, "")
    .replace(/\s+/g, " ")
    .replace(/^[ .-]+|[ .-]+$/g, "");
  return name.length <= 40 ? name : "";
}

const ManagerContext = createContext<() => void>(() => {});

/** Opens the tag manager from anywhere (the Library's tag bar, the tag picker). */
export const useTagManager = () => useContext(ManagerContext);

export function TagManagerProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <ManagerContext.Provider value={() => setOpen(true)}>
      {children}
      <Dialog open={open} onOpenChange={setOpen}>
        {open && <TagManager />}
      </Dialog>
    </ManagerContext.Provider>
  );
}

function useTagMutations() {
  const queryClient = useQueryClient();
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["tags"] });
    queryClient.invalidateQueries({ queryKey: ["items"] });
    queryClient.invalidateQueries({ queryKey: ["item"] });
  };
  const onError = (err: Error) => toast.error(err.message);
  return {
    create: useMutation({ mutationFn: ({ name, color }: { name: string; color: string }) => api.createTag(name, color), onSuccess: refresh, onError }),
    update: useMutation({
      mutationFn: ({ id, ...patch }: { id: number; name?: string; color?: string }) => api.updateTag(id, patch),
      onSuccess: refresh,
      onError,
    }),
    remove: useMutation({ mutationFn: (id: number) => api.deleteTag(id), onSuccess: refresh, onError }),
  };
}

function TagManager() {
  const tags = useQuery({ queryKey: ["tags"], queryFn: api.tags });
  const { create } = useTagMutations();
  const [name, setName] = useState("");
  const [color, setColor] = useState(() => PRESET_COLORS[Math.floor(Math.random() * PRESET_COLORS.length)]);
  const clean = cleanTag(name);
  const exists = tags.data?.some((t) => t.name === clean);

  return (
    <DialogContent className="flex max-h-[min(40rem,85vh)] flex-col gap-0 p-0 sm:max-w-md">
      <DialogHeader className="border-b p-4 pr-12">
        <DialogTitle className="font-heading text-xl font-medium">Tags</DialogTitle>
        <DialogDescription>Colors show wherever a tag appears. Tags you make here stay, even before anything uses them.</DialogDescription>
      </DialogHeader>

      <form
        className="flex items-center gap-2 border-b p-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!clean || exists) return;
          create.mutate(
            { name: clean, color },
            {
              onSuccess: () => {
                setName("");
                setColor(PRESET_COLORS[Math.floor(Math.random() * PRESET_COLORS.length)]);
              },
            },
          );
        }}
      >
        <ColorButton color={color} onDone={setColor} label="Color for the new tag" />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New tag"
          maxLength={40}
          aria-label="New tag name"
          className="h-8 min-w-0 flex-1 rounded-md border bg-background px-2.5 text-sm outline-none focus:border-brand/60"
        />
        <Button type="submit" size="sm" disabled={!clean || exists || create.isPending}>
          <Plus /> Add
        </Button>
      </form>
      {exists && <p className="px-4 pt-2 text-xs text-muted-foreground">#{clean} already exists.</p>}

      <ul className="min-h-0 flex-1 overflow-y-auto p-2" aria-label="Your tags">
        {tags.data?.length === 0 && <li className="p-4 text-center text-sm text-muted-foreground">No tags yet.</li>}
        {tags.data?.map((tag) => (
          <TagRow key={tag.id} tag={tag} all={tags.data} />
        ))}
      </ul>
    </DialogContent>
  );
}

function TagRow({ tag, all }: { tag: TagWithCount; all: TagWithCount[] }) {
  const { update, remove } = useTagMutations();
  const [name, setName] = useState(tag.name);
  const [mergeInto, setMergeInto] = useState<TagWithCount | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  function commit() {
    const clean = cleanTag(name);
    if (!clean) {
      setName(tag.name);
      return;
    }
    if (clean === tag.name) return;
    const other = all.find((t) => t.name === clean);
    if (other) setMergeInto(other);
    else update.mutate({ id: tag.id, name: clean });
  }

  const uses = `${tag.item_count} ${tag.item_count === 1 ? "item" : "items"}`;

  return (
    <li className="rounded-lg px-2 py-1.5 transition-colors duration-150 hover:bg-muted/50">
      <div className="flex items-center gap-2">
        <ColorButton color={tag.color} onDone={(color) => color !== tag.color && update.mutate({ id: tag.id, color })} label={`Color of #${tag.name}`} />
        <span className="text-sm text-muted-foreground" aria-hidden>
          #
        </span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
            if (e.key === "Escape") {
              e.stopPropagation(); // keep the dialog open; just undo the edit
              setName(tag.name);
              setMergeInto(null);
            }
          }}
          maxLength={40}
          aria-label={`Rename #${tag.name}`}
          className="-ml-1.5 h-7 min-w-0 flex-1 rounded-md border border-transparent bg-transparent px-1 text-sm outline-none hover:border-border focus:border-brand/60 focus:bg-background"
        />
        <span className="shrink-0 text-xs text-muted-foreground tabular-nums">{uses}</span>
        <Button size="icon-sm" variant="ghost" onClick={() => setConfirmDelete((v) => !v)} aria-label={`Delete #${tag.name}`} aria-expanded={confirmDelete}>
          <Trash2 />
        </Button>
      </div>

      {mergeInto && (
        <InlineConfirm
          text={`#${mergeInto.name} already exists. Merge #${tag.name} into it?`}
          action="Merge"
          onConfirm={() => {
            update.mutate({ id: tag.id, name: mergeInto.name });
            setMergeInto(null);
          }}
          onCancel={() => {
            setMergeInto(null);
            setName(tag.name);
          }}
        />
      )}
      {confirmDelete && (
        <InlineConfirm
          text={tag.item_count ? `Remove #${tag.name} from ${uses}? The items stay.` : `Delete #${tag.name}?`}
          action="Delete"
          destructive
          onConfirm={() => remove.mutate(tag.id)}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </li>
  );
}

function InlineConfirm({
  text,
  action,
  destructive,
  onConfirm,
  onCancel,
}: {
  text: string;
  action: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  return (
    <div role="alert" className="mt-1.5 ml-9 flex animate-enter flex-wrap items-center gap-2 text-xs">
      <span className="text-muted-foreground">{text}</span>
      <span className="ml-auto flex gap-1">
        <Button size="xs" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button size="xs" variant={destructive ? "destructive" : "default"} onClick={onConfirm}>
          {action}
        </Button>
      </span>
    </div>
  );
}

/** A swatch that opens the color wheel; the color is saved once the wheel closes. */
export function ColorButton({ color, onDone, label }: { color: string; onDone: (color: string) => void; label: string }) {
  const [draft, setDraft] = useState(color);
  return (
    <Popover
      onOpenChange={(open) => {
        if (open) setDraft(color);
        else onDone(draft);
      }}
    >
      <PopoverTrigger
        type="button"
        aria-label={label}
        className="grid size-7 shrink-0 place-items-center rounded-md transition-transform duration-150 ease-(--ease-out) hover:bg-muted active:scale-95"
      >
        <span className="size-4 rounded-full shadow-[inset_0_0_0_1px_rgb(0_0_0/0.15)]" style={{ background: color }} />
      </PopoverTrigger>
      <PopoverContent>
        <ColorWheel value={draft} onChange={setDraft} />
      </PopoverContent>
    </Popover>
  );
}
