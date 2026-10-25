/** Same-origin by default: next.config.ts proxies /api to the backend. */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export type ItemStatus = "queued" | "processing" | "ready" | "failed";
export type SourceType = "pdf" | "url" | "note" | "file" | "youtube";
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
  details: ItemDetails | null;
  note: string | null;
  tags_edited: boolean;
  status: ItemStatus;
  error: string | null;
  created_at: string;
  tags: Tag[];
  /** Only on search results: where the search matched inside the document. */
  match?: SearchMatch | null;
}

export interface SearchMatch {
  /** "text": the words occur in `snippet`; "related": close in topic (snippet is the summary). */
  kind: "text" | "related";
  /** Matched words are wrapped in MARK_START ... MARK_END. */
  snippet: string;
  page: number | null;
  chunk_id: number | null;
  start_char: number | null;
  end_char: number | null;
}

export const MARK_START = "\u2063[[";
export const MARK_END = "]]\u2063";

/** The page-long summary written when an item is processed. */
export interface ItemDetails {
  overview: string;
  key_points: string[];
  sections: { heading: string; body: string }[];
}

export interface User {
  id: number;
  email: string;
  name: string | null;
}

export interface Chunk {
  id: number;
  item_id: number;
  chunk_index: number;
  chunk_text: string;
  page: number | null;
  start_char: number | null;
  end_char: number | null;
}

export interface Page {
  page: number | null;
  text: string;
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
  start_char?: number | null;
  end_char?: number | null;
  /** "note" when the passage comes from your own notes on the item. */
  kind?: "text" | "note";
}

/** How a source is named to the reader: a document's title, or "Your notes on …". */
export const sourceName = (source: Pick<Source, "title" | "kind">) =>
  source.kind === "note" ? `Your notes on ${source.title}` : source.title;

export interface Highlight {
  id: number;
  item_id: number;
  start_char: number;
  end_char: number;
  quote: string;
  note: string | null;
  created_at: string;
}

export interface SearchResults {
  items: { id: number; title: string; source_type: SourceType; status: ItemStatus }[];
  passages: { item_id: number; title: string; text: string; page: number | null; start_char: number | null; end_char: number | null; kind: "text" | "note" }[];
  highlights: { id: number; item_id: number; item_title: string; quote: string; note: string | null; start_char: number; end_char: number }[];
  chats: { id: number; title: string }[];
  tags: string[];
}

export interface HighlightWithItem extends Highlight {
  item_title: string;
}

/** Where a citation opens: the item's reader, at the passage. The character range survives the
 *  item being processed again; the chunk id is the fallback for answers saved before ranges. */
export function passageHref(source: Pick<Source, "item_id" | "chunk_id" | "start_char" | "end_char" | "kind">) {
  if (source.kind === "note") return `/items/${source.item_id}?view=summary#notes`;
  if (source.start_char != null && source.end_char != null) {
    return `/items/${source.item_id}?from=${source.start_char}&to=${source.end_char}`;
  }
  return `/items/${source.item_id}?chunk=${source.chunk_id}`;
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

export interface ChatSummary {
  id: number;
  title: string;
  item_id: number | null;
  item_title: string | null;
  message_count: number;
  updated_at: string;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: Source[] | null;
  cited: number[] | null;
  not_found: boolean;
  search_query: string | null;
  created_at: string;
}

export interface Chat {
  id: number;
  title: string;
  item_id: number | null;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface MessageDone extends AskDone {
  message_ids: [number, number];
  title: string;
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
  if (res.status === 401 && !path.startsWith("/auth/")) {
    // The session expired or was signed out elsewhere: go and sign in, then come back.
    const next = window.location.pathname + window.location.search;
    window.location.assign(`/login?next=${encodeURIComponent(next)}`);
    throw new ApiError("Please log in.", 401);
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
  items: (tag?: string, q?: string) => {
    const params = new URLSearchParams();
    if (tag) params.set("tag", tag);
    if (q) params.set("q", q);
    return request<Item[]>(params.size ? `/items?${params}` : "/items");
  },
  item: (id: number) => request<Item>(`/items/${id}`),
  tags: () => request<TagWithCount[]>("/tags"),
  chunk: (id: number) => request<Chunk>(`/chunks/${id}`),
  content: (id: number) => request<{ pages: Page[] }>(`/items/${id}/content`),
  setNote: (id: number, note: string) => request<Item>(`/items/${id}/note`, json("PUT", { note })),
  search: (q: string) => request<SearchResults>(`/search?q=${encodeURIComponent(q)}`),
  highlights: (itemId: number) => request<Highlight[]>(`/items/${itemId}/highlights`),
  allHighlights: () => request<HighlightWithItem[]>("/highlights"),
  addHighlight: (itemId: number, start: number, end: number, note?: string) =>
    request<Highlight>(`/items/${itemId}/highlights`, json("POST", { start_char: start, end_char: end, note: note ?? null })),
  editHighlight: (id: number, note: string) => request<Highlight>(`/highlights/${id}`, json("PATCH", { note })),
  deleteHighlight: (id: number) => request<void>(`/highlights/${id}`, { method: "DELETE" }),
  saveUrl: (url: string) => {
    const form = new FormData();
    form.append("url", url);
    return request<Item>("/items", { method: "POST", body: form });
  },
  saveFile: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<Item>("/items", { method: "POST", body: form });
  },
  saveNote: (text: string, title?: string) => {
    const form = new FormData();
    form.append("text", text);
    if (title) form.append("title", title);
    return request<Item>("/items", { method: "POST", body: form });
  },
  reprocess: (id: number) => request<Item>(`/items/${id}/reprocess`, { method: "POST" }),
  remove: (id: number) => request<void>(`/items/${id}`, { method: "DELETE" }),
  setTags: (id: number, tags: string[]) => request<Item>(`/items/${id}/tags`, json("PUT", { tags })),

  me: () => request<User>("/auth/me"),
  signup: (email: string, password: string, name?: string) => request<User>("/auth/signup", json("POST", { email, password, name })),
  login: (email: string, password: string) => request<User>("/auth/login", json("POST", { email, password })),
  logout: () => request<void>("/auth/logout", { method: "POST" }),

  chats: () => request<ChatSummary[]>("/chats"),
  chat: (id: number) => request<Chat>(`/chats/${id}`),
  createChat: (itemId?: number) => request<Chat>("/chats", json("POST", { item_id: itemId ?? null })),
  renameChat: (id: number, title: string) => request<Chat>(`/chats/${id}`, json("PATCH", { title })),
  deleteChat: (id: number) => request<void>(`/chats/${id}`, { method: "DELETE" }),
};

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export const fileUrl = (itemId: number, page?: number | null) =>
  `${API_URL}/items/${itemId}/file${page ? `#page=${page}` : ""}`;

/** Where "open source" goes: the stored PDF (at a page, if known) or the original link. */
/** Where "open original" goes: the stored file (a PDF at a page, if known), the video at the
 *  passage's time, or the original link. Notes have no original: null. */
export function sourceHref(item: { source_type: SourceType; source: string }, itemId: number, page?: number | null, passage?: string) {
  if (item.source_type === "note") return null;
  if (item.source_type === "pdf" || item.source_type === "file") return fileUrl(itemId, item.source_type === "pdf" ? page : null);
  if (item.source_type === "youtube") {
    const seconds = passage ? secondsAt(passage) : null;
    if (seconds === null) return item.source;
    const url = new URL(item.source);
    url.searchParams.set("t", `${seconds}s`);
    return url.toString();
  }
  if (page && /\.pdf($|[?#])|arxiv\.org\/pdf\//i.test(item.source)) return `${item.source}#page=${page}`;
  return item.source;
}

/** The first "[m:ss]" or "[h:mm:ss]" timestamp in a video passage, in seconds. */
function secondsAt(text: string) {
  const match = /\[(?:(\d+):)?(\d{1,2}):(\d{2})\]/.exec(text);
  if (!match) return null;
  return Number(match[1] ?? 0) * 3600 + Number(match[2]) * 60 + Number(match[3]);
}

export const isBusy = (status: ItemStatus) => status === "queued" || status === "processing";

export interface StreamHandlers<Done> {
  onQuery?: (query: string) => void;
  onSources: (sources: Source[]) => void;
  onDelta: (text: string) => void;
  onDone: (done: Done) => void;
  onError: (message: string) => void;
}

/** Ask the next question in a saved chat; the answer streams back as Server-Sent Events. */
export function sendChatMessage(chatId: number, question: string, handlers: StreamHandlers<MessageDone>, signal?: AbortSignal) {
  return postStream(`/chats/${chatId}/messages`, { question }, handlers, signal);
}

/** POST and parse Server-Sent Events (EventSource can't send a POST body). */
async function postStream<Done>(path: string, body: unknown, handlers: StreamHandlers<Done>, signal?: AbortSignal) {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...json("POST", body), signal });
  } catch (err) {
    if ((err as Error).name === "AbortError") return;
    handlers.onError("Can't reach the Recall API. Is the backend running?");
    return;
  }
  if (!res.ok || !res.body) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
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
      if (event === "query") handlers.onQuery?.(payload.query);
      else if (event === "sources") handlers.onSources(payload.sources);
      else if (event === "delta") handlers.onDelta(payload.text);
      else if (event === "done") handlers.onDone(payload);
      else if (event === "error") handlers.onError(payload.message);
    }
  }
}
