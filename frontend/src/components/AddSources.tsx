"use client";

import { useQueryClient } from "@tanstack/react-query";
import { FileUp, Link2, Loader2, NotebookPen } from "lucide-react";
import { useRouter } from "next/navigation";
import { useId, useRef, useState } from "react";
import { toast } from "sonner";
import { NotePictures, PictureButton, usePictureInsert, withoutPicture } from "@/components/Pictures";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type Item } from "@/lib/api";
import { cn } from "@/lib/utils";

const MAX_MB = 25;
const EXTENSIONS = [".pdf", ".docx", ".md", ".markdown", ".txt"];

/** Files, links (one per line) or a typed note. After saving, goes to the item (one) or the
 *  library (several). */
export function AddSources() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);

  async function save(tasks: (() => Promise<Item>)[]) {
    setBusy(true);
    const saved: Item[] = [];
    for (const task of tasks) {
      try {
        saved.push(await task());
      } catch (err) {
        toast.error((err as Error).message);
      }
    }
    setBusy(false);
    if (saved.length === 0) return false;
    queryClient.invalidateQueries({ queryKey: ["items"] });
    if (saved.length === 1) {
      toast.success("Saved. Recall is reading it now.");
      router.push(`/items/${saved[0].id}`);
    } else {
      toast.success(`Saved ${saved.length} items. Recall is reading them now.`);
      router.push("/");
    }
    return true;
  }

  return (
    <Tabs defaultValue="file" className="gap-4">
      <TabsList>
        <TabsTrigger value="file">
          <FileUp /> Files
        </TabsTrigger>
        <TabsTrigger value="url">
          <Link2 /> Links
        </TabsTrigger>
        <TabsTrigger value="note">
          <NotebookPen /> Note
        </TabsTrigger>
      </TabsList>
      <TabsContent value="file">
        <FileDrop busy={busy} onFiles={(files) => save(files.map((f) => () => api.saveFile(f)))} />
      </TabsContent>
      <TabsContent value="url">
        <LinksForm busy={busy} onUrls={(urls) => save(urls.map((u) => () => api.saveUrl(u)))} />
      </TabsContent>
      <TabsContent value="note">
        <NoteForm busy={busy} onNote={(text, title) => save([() => api.saveNote(text, title)])} />
      </TabsContent>
    </Tabs>
  );
}

function FileDrop({ busy, onFiles }: { busy: boolean; onFiles: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function accept(list: FileList | null) {
    const files = Array.from(list ?? []);
    const readable = files.filter((f) => EXTENSIONS.some((ext) => f.name.toLowerCase().endsWith(ext)));
    if (readable.length < files.length) toast.error("Recall can read PDF, Word (.docx), Markdown and text files.");
    const small = readable.filter((f) => f.size <= MAX_MB * 1024 * 1024);
    if (small.length < readable.length) toast.error(`Files must be ${MAX_MB} MB or smaller.`);
    if (small.length) onFiles(small);
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setOver(false);
        if (!busy) accept(e.dataTransfer.files);
      }}
      className={cn(
        "flex flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-colors",
        over ? "border-brand bg-brand-soft/60" : "border-border bg-card shadow-xs",
      )}
    >
      {busy ? (
        <Loader2 className="size-8 animate-spin text-brand" aria-hidden />
      ) : (
        <span className="grid size-12 place-items-center rounded-full bg-brand-soft text-brand">
          <FileUp className="size-5" aria-hidden />
        </span>
      )}
      <p className="mt-4 font-medium">{busy ? "Uploading…" : "Drop files here"}</p>
      <p className="mt-1 text-sm text-muted-foreground">PDF, Word, Markdown or text, up to {MAX_MB} MB each. Scanned images can&apos;t be read yet.</p>
      <Button className="mt-5" variant="outline" disabled={busy} onClick={() => input.current?.click()}>
        Choose files
      </Button>
      <input
        ref={input}
        type="file"
        accept={EXTENSIONS.join(",")}
        multiple
        hidden
        aria-label="Choose files"
        onChange={(e) => {
          accept(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}

/** Links, one per line, so a whole reading list can be pasted at once. */
function LinksForm({ busy, onUrls }: { busy: boolean; onUrls: (urls: string[]) => void }) {
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const id = useId();

  function submit() {
    const urls: string[] = [];
    const bad: string[] = [];
    for (const raw of text.split(/\s+/).map((l) => l.trim()).filter(Boolean)) {
      const value = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
      try {
        const url = new URL(value);
        if (!url.hostname.includes(".")) throw new Error();
        urls.push(url.toString());
      } catch {
        bad.push(raw);
      }
    }
    if (bad.length) {
      setError(`${bad.length === 1 ? "This doesn't" : "These don't"} look like links: ${bad.slice(0, 3).join(", ")}`);
      return;
    }
    setError(null);
    if (urls.length) onUrls([...new Set(urls)]);
  }

  return (
    <form
      className="space-y-3 rounded-2xl border bg-card shadow-xs p-6"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <label htmlFor={id} className="text-sm font-medium">
        Links to articles, PDFs or YouTube videos
      </label>
      <textarea
        id={id}
        autoFocus
        rows={3}
        placeholder={"https://…\nOne per line to save several at once"}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit();
        }}
        aria-invalid={!!error}
        aria-describedby={`${id}-help`}
        className="block w-full resize-y rounded-lg border bg-background px-3 py-2 text-[15px] outline-none focus:border-brand/60 focus:ring-3 focus:ring-brand/15"
      />
      <div className="flex items-start justify-between gap-4">
        <p id={`${id}-help`} className={cn("text-sm", error ? "text-destructive" : "text-muted-foreground")}>
          {error ?? "Blog posts, docs, Wikipedia, arXiv, YouTube (from its captions). Pages behind a login can't be read."}
        </p>
        <Button type="submit" size="lg" className="h-10 shrink-0" disabled={busy || !text.trim()}>
          {busy && <Loader2 className="animate-spin" />} Save
        </Button>
      </div>
    </form>
  );
}

function NoteForm({ busy, onNote }: { busy: boolean; onNote: (text: string, title?: string) => void }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const id = useId();
  const box = useRef<HTMLTextAreaElement>(null);
  // Pictures are uploaded as they're added and attached to the note when it's saved.
  const pictures = usePictureInsert({ textarea: box, value: text, onChange: setText });
  return (
    <form
      className="space-y-3 rounded-2xl border bg-card shadow-xs p-6"
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim()) onNote(text, title.trim() || undefined);
      }}
    >
      <div className="space-y-1.5">
        <label htmlFor={`${id}-title`} className="text-sm font-medium">
          Title <span className="font-normal text-muted-foreground">(optional)</span>
        </label>
        <Input id={`${id}-title`} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Lecture 5 notes" className="h-10" />
      </div>
      <div className="space-y-1.5">
        <label htmlFor={`${id}-text`} className="text-sm font-medium">
          Note
        </label>
        <textarea
          id={`${id}-text`}
          ref={box}
          rows={8}
          value={text}
          maxLength={200000}
          onChange={(e) => setText(e.target.value)}
          {...pictures.handlers}
          placeholder="Paste or write anything: lecture notes, an email, a passage from a book… Paste or drop pictures too."
          className="block w-full resize-y rounded-lg border bg-background px-3 py-2 text-[15px] leading-relaxed outline-none focus:border-brand/60 focus:ring-3 focus:ring-brand/15"
        />
        <NotePictures text={text} onRemove={(pid) => setText(withoutPicture(text, pid))} />
      </div>
      <div className="flex items-center justify-between gap-3">
        <PictureButton onFiles={pictures.add} busy={pictures.uploading} />
        <Button type="submit" size="lg" className="h-10" disabled={busy || pictures.uploading || !text.trim()}>
          {busy && <Loader2 className="animate-spin" />} Save note
        </Button>
      </div>
    </form>
  );
}
