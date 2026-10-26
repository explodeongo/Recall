/** Same-origin by default: next.config.ts proxies /api to the backend. */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export type ItemStatus = "queued" | "processing" | "ready" | "failed";
export type SourceType = "pdf" | "url" | "note" | "file" | "youtube";
export type SearchMode = "hybrid" | "vector" | "keyword";

export interface Tag {
  id: number;
  name: string;
  /** "#rrggbb": chosen in the tag manager, or a stable default picked from the name. */
  color: string;
}

export interface TagWithCount extends Tag {
  item_count: number;
  /** Made in the tag manager, so it stays even when no item uses it. */
  user_made: boolean;
}

export type TagMatch = "all" | "any";

export interface ItemFilter {
  tags?: string[];
  match?: TagMatch;
  q?: string;
  view?: "all" | "starred" | "archived";
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
  /** The picture shown for it in lists: an article's preview, a video's thumbnail, a PDF's first page. */
  cover_url: string | null;
  starred: boolean;
  archived: boolean;
  last_opened_at: string | null;
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

/** A picture: a figure from the document, or one added to a note. `url` is an API path. */
export interface Picture {
  id: number;
  url: string;
  width: number;
  height: number;
  alt: string | null;
  page?: number | null;
  /** Where it sits in the full text (offsets as for passages); null when it isn't placed. */
  position?: number | null;
  role?: "cover" | "figure" | "upload";
}

/** A term in an item's text that other saved items are about ("linked ideas"). */
export interface LinkedIdea {
  term: string;
  start: number;
  end: number;
  targets: {
    item_id: number;
    title: string;
    cover_url: string | null;
    snippet: string | null;
    chunk_id: number | null;
    start_char: number | null;
    end_char: number | null;
  }[];
}

/** Where to load an API image path from (cookies ride along: it's the app's own /api). */
export function imageSrc(path: string) {
  return `${API_URL}${path}`;
}

/** How notes refer to an added picture: ![what it shows](image:12) */
export const IMAGE_TOKEN = /!\[([^\]\n]{0,300})\]\(image:(\d+)\)/g;

/** One numbered passage given to the model; answers cite it as [n]. */
export interface Source {
  n: number;
  /** Null for web passages, whose `source` is the page's address. */
  chunk_id: number | null;
  item_id: number | null;
  title: string;
  source_type: SourceType;
  source: string;
  page: number | null;
  text: string;
  start_char?: number | null;
  end_char?: number | null;
  /** "note": your own notes on the item. "web": a web page found for the question. */
  kind?: "text" | "note" | "web";
  /** Figures beside the passage in its document (library sources only). */
  images?: { id: number; alt: string | null; width: number; height: number }[];
}

/** How a source is named to the reader: a document's title, or "Your notes on …". */
export const sourceName = (source: Pick<Source, "title" | "kind">) =>
  source.kind === "note" ? `Your notes on ${source.title}` : source.title;

/** "en.wikipedia.org" from a URL, for labelling web sources. */
export function siteOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

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

export type Grade = "again" | "hard" | "good" | "easy";

export type CardKind = "flashcard" | "multiple_choice" | "true_false";
export type CardStage = "new" | "learning" | "practiced" | "confident" | "mastered";

export interface Card {
  id: number;
  item_id: number;
  /** Flashcards are recalled and self-graded; the other kinds are answered by picking an option. */
  kind: CardKind;
  question: string;
  /** For choice questions, the right option word for word. */
  answer: string;
  options: string[] | null;
  explanation: string | null;
  start_char: number | null;
  end_char: number | null;
  due_at: string;
  interval_days: number;
  reps: number;
  lapses: number;
  last_reviewed_at: string | null;
  stage: CardStage;
}

export interface DueCard extends Card {
  item_title: string;
  /** When the card would come back for each grade, e.g. { again: "10m", good: "1d" }. */
  next: Record<Grade, string>;
}

export interface ReviewStats {
  due: number;
  total: number;
  reviewed_today: number;
  streak_days: number;
  next_due_at: string | null;
}

export interface HighlightWithItem extends Highlight {
  item_title: string;
}

/** Where a citation opens: the item's reader, at the passage. The character range survives the
 *  item being processed again; the chunk id is the fallback for answers saved before ranges. */
export function passageHref(source: Pick<Source, "item_id" | "chunk_id" | "start_char" | "end_char" | "kind"> & { source?: string }) {
  if (source.kind === "web") return source.source ?? "#";
  if (source.kind === "note") return `/items/${source.item_id}?view=summary#notes`;
  if (source.start_char != null && source.end_char != null) {
    return `/items/${source.item_id}?from=${source.start_char}&to=${source.end_char}`;
  }
  return `/items/${source.item_id}?chunk=${source.chunk_id}`;
}

/** A personal access token for the API and AI assistants (MCP). The token itself is shown once. */
export interface ApiToken {
  id: number;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
}

export interface Connection {
  item: Item;
  similarity: number;
  shared_tags: string[];
  /** The passage in the connected item closest to this one. */
  passage: { chunk_id: number; text: string; page: number | null; start_char: number | null; end_char: number | null } | null;
}

export interface GraphNode {
  id: number;
  title: string;
  source_type: SourceType;
  tags: Tag[];
  created_at: string;
  /** The topic group it belongs to; null when it's linked to nothing (or only loosely). */
  cluster: number | null;
}

export interface GraphCluster {
  id: number;
  /** The tag most of its items share, if any. */
  label: string | null;
  size: number;
  color: string | null;
}

export interface Graph {
  clusters: GraphCluster[];
  nodes: GraphNode[];
  edges: { source: number; target: number; similarity: number }[];
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
  /** On questions: what the answer was limited to ("@" items and tags) and where it could come from. */
  context?: MessageContext | null;
  /** On answers kept in the library: the note they became. */
  saved_item_id?: number | null;
  created_at: string;
}

/** Where answers may come from: the library, the library then the web, or only the web. */
export type AnswerSource = "library" | "both" | "web";

export interface MessageContext {
  items: { id: number; title: string }[];
  tags: string[];
  source: AnswerSource;
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
  /** Whether part of the answer came from web pages rather than the library. */
  web_used: boolean;
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
  items: ({ tags, match, q, view }: ItemFilter = {}) => {
    const params = new URLSearchParams();
    if (tags?.length) params.set("tags", tags.join(","));
    if (tags && tags.length > 1 && match === "any") params.set("match", "any");
    if (q) params.set("q", q);
    if (view && view !== "all") params.set("view", view);
    return request<Item[]>(params.size ? `/items?${params}` : "/items");
  },
  item: (id: number) => request<Item>(`/items/${id}`),
  connections: (id: number) => request<Connection[]>(`/items/${id}/connections`),
  graph: () => request<Graph>("/graph"),
  tags: () => request<TagWithCount[]>("/tags"),
  createTag: (name: string, color?: string) => request<TagWithCount>("/tags", json("POST", { name, color })),
  updateTag: (id: number, patch: { name?: string; color?: string }) => request<TagWithCount>(`/tags/${id}`, json("PATCH", patch)),
  deleteTag: (id: number) => request<void>(`/tags/${id}`, { method: "DELETE" }),
  chunk: (id: number) => request<Chunk>(`/chunks/${id}`),
  content: (id: number) => request<{ pages: Page[]; images: Picture[] }>(`/items/${id}/content`),
  links: (id: number) => request<LinkedIdea[]>(`/items/${id}/links`),
  uploadImage: (file: File, itemId?: number, alt?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (itemId !== undefined) form.append("item_id", String(itemId));
    if (alt) form.append("alt", alt);
    return request<Picture>("/images", { method: "POST", body: form });
  },
  setNote: (id: number, note: string) => request<Item>(`/items/${id}/note`, json("PUT", { note })),
  generateCards: (itemId: number) => request<Card[]>(`/items/${itemId}/cards`, { method: "POST" }),
  itemCards: (itemId: number) => request<Card[]>(`/items/${itemId}/cards`),
  dueCards: (itemId?: number) => request<DueCard[]>(itemId ? `/review?item_id=${itemId}` : "/review"),
  reviewCard: (id: number, grade: Grade) => request<Card>(`/cards/${id}/review`, json("POST", { grade })),
  reviewStats: () => request<ReviewStats>(`/review/stats?tz_offset=${-new Date().getTimezoneOffset()}`),
  editCard: (id: number, question: string, answer: string) => request<Card>(`/cards/${id}`, json("PATCH", { question, answer })),
  deleteCard: (id: number) => request<void>(`/cards/${id}`, { method: "DELETE" }),
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
  patchItem: (id: number, patch: { title?: string; starred?: boolean; archived?: boolean }) => request<Item>(`/items/${id}`, json("PATCH", patch)),
  markOpened: (id: number) => request<void>(`/items/${id}/opened`, { method: "POST" }),
  resurface: () => request<{ items: Item[]; cards_due: number }>("/items/resurface"),
  reprocess: (id: number) => request<Item>(`/items/${id}/reprocess`, { method: "POST" }),
  remove: (id: number) => request<void>(`/items/${id}`, { method: "DELETE" }),
  setTags: (id: number, tags: string[]) => request<Item>(`/items/${id}/tags`, json("PUT", { tags })),

  me: () => request<User>("/auth/me"),
  signup: (email: string, password: string, name?: string, inviteCode?: string) =>
    request<User>("/auth/signup", json("POST", { email, password, name, invite_code: inviteCode })),
  authConfig: () => request<{ signup_requires_code: boolean; mcp_url: string }>("/auth/config"),
  apiTokens: () => request<ApiToken[]>("/auth/tokens"),
  createApiToken: (name: string) => request<ApiToken & { token: string }>("/auth/tokens", json("POST", { name })),
  revokeApiToken: (id: number) => request<void>(`/auth/tokens/${id}`, { method: "DELETE" }),
  login: (email: string, password: string) => request<User>("/auth/login", json("POST", { email, password })),
  logout: () => request<void>("/auth/logout", { method: "POST" }),

  saveAnswer: (chatId: number, messageId: number) => request<Item>(`/chats/${chatId}/messages/${messageId}/save`, { method: "POST" }),
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
  /** Progress, such as "Searching the web…". */
  onStatus?: (text: string) => void;
  onSources: (sources: Source[]) => void;
  onDelta: (text: string) => void;
  onDone: (done: Done) => void;
  onError: (message: string) => void;
}

/** Ask the next question in a saved chat; the answer streams back as Server-Sent Events. */
export function sendChatMessage(chatId: number, question: string, context: MessageContext, handlers: StreamHandlers<MessageDone>, signal?: AbortSignal) {
  const body = { question, source: context.source, item_ids: context.items.map((i) => i.id), tags: context.tags };
  return postStream(`/chats/${chatId}/messages`, body, handlers, signal);
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
      else if (event === "status") handlers.onStatus?.(payload.text);
      else if (event === "sources") handlers.onSources(payload.sources);
      else if (event === "delta") handlers.onDelta(payload.text);
      else if (event === "done") handlers.onDone(payload);
      else if (event === "error") handlers.onError(payload.message);
    }
  }
}
