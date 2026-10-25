import Link from "next/link";
import { api, type Item, type TagWithCount } from "@/lib/api";

const statusStyle: Record<Item["status"], string> = {
  queued: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
  processing: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  ready: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
};

export default async function LibraryPage({ searchParams }: { searchParams: Promise<{ tag?: string }> }) {
  const { tag } = await searchParams;
  let items: Item[] = [];
  let tags: TagWithCount[] = [];
  let error: string | null = null;
  try {
    [items, tags] = await Promise.all([api.items(tag), api.tags()]);
  } catch {
    error = "Can't reach the Recall API. Is the backend running?";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">Library</h1>
        <Link href="/add" className="rounded-md bg-zinc-900 px-3 py-1.5 text-sm text-white dark:bg-zinc-100 dark:text-zinc-900">
          Add item
        </Link>
      </div>

      {tags.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <Link href="/" className={`rounded-full border px-3 py-1 text-sm ${!tag ? "border-zinc-900 dark:border-zinc-100" : "border-zinc-300 dark:border-zinc-700"}`}>
            All
          </Link>
          {tags.map((t) => (
            <Link
              key={t.id}
              href={`/?tag=${encodeURIComponent(t.name)}`}
              className={`rounded-full border px-3 py-1 text-sm ${tag === t.name ? "border-zinc-900 dark:border-zinc-100" : "border-zinc-300 dark:border-zinc-700"}`}
            >
              {t.name} <span className="text-zinc-500">{t.item_count}</span>
            </Link>
          ))}
        </div>
      )}

      {error && <p className="rounded-md border border-red-300 p-3 text-sm text-red-700 dark:border-red-900 dark:text-red-400">{error}</p>}

      {!error && items.length === 0 && (
        <p className="text-zinc-500">Nothing saved yet. Add a PDF or an article link to get started.</p>
      )}

      <ul className="divide-y divide-zinc-200 dark:divide-zinc-800">
        {items.map((item) => (
          <li key={item.id} className="py-4">
            <div className="flex items-center gap-3">
              <span className="text-xs uppercase text-zinc-500">{item.source_type}</span>
              <span className="font-medium">{item.title}</span>
              <span className={`ml-auto rounded px-2 py-0.5 text-xs ${statusStyle[item.status]}`}>{item.status}</span>
            </div>
            {item.summary && <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{item.summary}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
