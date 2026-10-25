"use client";

import { useQueryClient } from "@tanstack/react-query";
import { FileUp, Link2, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, type Item } from "@/lib/api";
import { cn } from "@/lib/utils";

const MAX_MB = 25;

/** Upload PDFs or paste a link. After saving, goes to the item (one) or the library (several). */
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
    if (saved.length === 0) return;
    queryClient.invalidateQueries({ queryKey: ["items"] });
    if (saved.length === 1) {
      toast.success("Saved. Recall is reading it now.");
      router.push(`/items/${saved[0].id}`);
    } else {
      toast.success(`Saved ${saved.length} items. Recall is reading them now.`);
      router.push("/");
    }
  }

  return (
    <Tabs defaultValue="pdf" className="gap-4">
      <TabsList>
        <TabsTrigger value="pdf">
          <FileUp /> Upload PDF
        </TabsTrigger>
        <TabsTrigger value="url">
          <Link2 /> Paste link
        </TabsTrigger>
      </TabsList>
      <TabsContent value="pdf">
        <PdfDrop busy={busy} onFiles={(files) => save(files.map((f) => () => api.savePdf(f)))} />
      </TabsContent>
      <TabsContent value="url">
        <UrlForm busy={busy} onUrl={(url) => save([() => api.saveUrl(url)])} />
      </TabsContent>
    </Tabs>
  );
}

function PdfDrop({ busy, onFiles }: { busy: boolean; onFiles: (files: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  function accept(list: FileList | null) {
    const files = Array.from(list ?? []);
    const pdfs = files.filter((f) => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length < files.length) toast.error("Only PDF files can be uploaded.");
    const small = pdfs.filter((f) => f.size <= MAX_MB * 1024 * 1024);
    if (small.length < pdfs.length) toast.error(`PDFs must be ${MAX_MB} MB or smaller.`);
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
        over ? "border-brand bg-brand-soft/60" : "border-border bg-card",
      )}
    >
      {busy ? (
        <Loader2 className="size-8 animate-spin text-brand" aria-hidden />
      ) : (
        <span className="grid size-12 place-items-center rounded-full bg-brand-soft text-brand">
          <FileUp className="size-5" aria-hidden />
        </span>
      )}
      <p className="mt-4 font-medium">{busy ? "Uploading…" : "Drop PDFs here"}</p>
      <p className="mt-1 text-sm text-muted-foreground">Text-based PDFs up to {MAX_MB} MB. Scanned images can&apos;t be read yet.</p>
      <Button className="mt-5" variant="outline" disabled={busy} onClick={() => input.current?.click()}>
        Choose files
      </Button>
      <input
        ref={input}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        hidden
        aria-label="Choose PDF files"
        onChange={(e) => {
          accept(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}

function UrlForm({ busy, onUrl }: { busy: boolean; onUrl: (url: string) => void }) {
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  return (
    <form
      className="space-y-3 rounded-2xl border bg-card p-6"
      onSubmit={(e) => {
        e.preventDefault();
        let value = url.trim();
        if (value && !/^https?:\/\//i.test(value)) value = `https://${value}`;
        try {
          new URL(value);
        } catch {
          setError("That doesn't look like a link. Try something like https://example.com/article");
          return;
        }
        setError(null);
        onUrl(value);
      }}
    >
      <label htmlFor="url" className="text-sm font-medium">
        Article or PDF link
      </label>
      <div className="flex gap-2">
        <Input
          id="url"
          type="text"
          inputMode="url"
          autoFocus
          placeholder="https://…"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          aria-invalid={!!error}
          aria-describedby={error ? "url-error" : "url-hint"}
          className="h-10"
        />
        <Button type="submit" size="lg" className="h-10" disabled={busy || !url.trim()}>
          {busy && <Loader2 className="animate-spin" />} Save
        </Button>
      </div>
      {error ? (
        <p id="url-error" className="text-sm text-destructive">
          {error}
        </p>
      ) : (
        <p id="url-hint" className="text-sm text-muted-foreground">
          Blog posts, docs, Wikipedia, arXiv papers. Pages behind a login can&apos;t be read.
        </p>
      )}
    </form>
  );
}
