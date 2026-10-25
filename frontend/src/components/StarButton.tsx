"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Star } from "lucide-react";
import { toast } from "sonner";
import { api, type Item } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Star or unstar an item, in place. */
export function StarButton({ item, className }: { item: Item; className?: string }) {
  const queryClient = useQueryClient();
  const star = useMutation({
    mutationFn: () => api.patchItem(item.id, { starred: !item.starred }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["item", item.id], updated);
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
    onError: (err) => toast.error(err.message),
  });
  const starred = star.isPending ? !item.starred : item.starred;
  return (
    <button
      onClick={() => star.mutate()}
      aria-pressed={starred}
      aria-label={starred ? "Unstar" : "Star"}
      className={cn(
        "grid size-7 place-items-center rounded-md transition-[color,background-color,transform] duration-150 hover:bg-muted active:scale-[0.9]",
        starred ? "text-amber-500" : "text-muted-foreground/60 hover:text-foreground",
        className,
      )}
    >
      <Star className={cn("size-4", starred && "fill-current")} aria-hidden />
    </button>
  );
}

