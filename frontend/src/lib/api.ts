export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ItemStatus = "queued" | "processing" | "ready" | "failed";
export type SourceType = "pdf" | "url";
export type SearchMode = "hybrid" | "vector" | "keyword";

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
  source_type: SourceType;
  source: string;
  summary: string | null;
  status: ItemStatus;
  error: string | null;
  created_at: string;
  tags: Tag[];
}

export interface Chunk {
  id: number;
  item_id: number;
  chunk_index: number;
  chunk_text: string;
  page: number | null;
}

/** One numbered passage given to the model; answers cite it as [n]. */
export interface Source {
  n: number;
  chunk_id: number;
  item_id: number;
  title: string;
  source_type: SourceType;
  source: string;
  page: number | null;
  text: string;
}

export interface Timings {
  retrieval_ms: number;
  llm_ms: number;
  first_token_ms: number | null;
}

export interface AskDone {
  answer: string;
  not_found: boolean;
  cited: number[];
  timings: Timings;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError("Can't reach the Recall API. Is the backend running?", 0);
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {}
    throw new ApiError(detail, res.status);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  items: (tag?: string) => request<Item[]>(tag ? `/items?tag=${encodeURIComponent(tag)}` : "/items"),
  item: (id: number) => request<Item>(`/items/${id}`),
  tags: () => request<TagWithCount[]>("/tags"),
  chunk: (id: number) => request<Chunk>(`/chunks/${id}`),
  saveUrl: (url: string) => {
    const form = new FormData();
    form.append("url", url);
    return request<Item>("/items", { method: "POST", body: form });
  },
  savePdf: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Item>("/items", { method: "POST", body: form });
  },
  reprocess: (id: number) => request<Item>(`/items/${id}/reprocess`, { method: "POST" }),
  remove: (id: number) => request<void>(`/items/${id}`, { method: "DELETE" }),
};

export const fileUrl = (itemId: number, page?: number | null) =>
  `${API_URL}/items/${itemId}/file${page ? `#page=${page}` : ""}`;

/** Where "open source" goes: the stored PDF (at a page, if known) or the original link. */
export function sourceHref(item: { source_type: SourceType; source: string }, itemId: number, page?: number | null) {
  if (item.source_type === "pdf") return fileUrl(itemId, page);
  if (page && /\.pdf($|[?#])|arxiv\.org\/pdf\//i.test(item.source)) return `${item.source}#page=${page}`;
  return item.source;
}

export const isBusy = (status: ItemStatus) => status === "queued" || status === "processing";

export interface AskHandlers {
  onSources: (sources: Source[]) => void;
  onDelta: (text: string) => void;
  onDone: (done: AskDone) => void;
  onError: (message: string) => void;
}

/** POST /ask/stream and parse its Server-Sent Events (EventSource can't send a POST body). */
export async function askStream(question: string, handlers: AskHandlers, signal?: AbortSignal) {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    handlers.onError("Can't reach the Recall API. Is the backend running?");
    return;
  }
  if (!res.ok || !res.body) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {}
    handlers.onError(detail);
    return;
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "sources") handlers.onSources(payload.sources);
      else if (event === "delta") handlers.onDelta(payload.text);
      else if (event === "done") handlers.onDone(payload);
      else if (event === "error") handlers.onError(payload.message);
    }
  }
}
