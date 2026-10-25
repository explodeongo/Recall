export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ItemStatus = "queued" | "processing" | "ready" | "failed";

export interface Tag {
  id: number;
  name: string;
}

export interface TagWithCount extends Tag {
  item_count: number;
}

export interface Item {
  id: number;
  title: string;
  source_type: "pdf" | "url";
  source: string;
  summary: string | null;
  status: ItemStatus;
  error: string | null;
  created_at: string;
  tags: Tag[];
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} failed with ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  items: (tag?: string) => get<Item[]>(tag ? `/items?tag=${encodeURIComponent(tag)}` : "/items"),
  item: (id: number) => get<Item>(`/items/${id}`),
  tags: () => get<TagWithCount[]>("/tags"),
};
