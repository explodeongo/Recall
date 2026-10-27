import { Skeleton } from "@/components/ui/skeleton";

/** Shown while a page's code arrives, so a click always answers with something. The skeleton
 * stays invisible for its first 150 ms, so quick switches don't flash. */
export default function Loading() {
  return (
    <div className="mx-auto max-w-4xl space-y-6" aria-busy="true" aria-label="Loading">
      <Skeleton className="h-9 w-2/3 rounded-lg" />
      <div className="space-y-2.5">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-11/12" />
        <Skeleton className="h-4 w-4/5" />
      </div>
      <Skeleton className="h-40 w-full rounded-xl" />
    </div>
  );
}
