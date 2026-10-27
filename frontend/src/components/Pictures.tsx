"use client";

import { ImagePlus, Loader2, X } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";
import { SourceIcon } from "@/components/ItemBits";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { IMAGE_TOKEN, api, imageSrc, type Item, type Picture } from "@/lib/api";
import { cn } from "@/lib/utils";

/** A figure that opens full size when clicked. */
export function Figure({ picture, caption, className }: { picture: Pick<Picture, "url" | "width" | "height" | "alt">; caption?: string | null; className?: string }) {
  const [open, setOpen] = useState(false);
  const text = caption ?? picture.alt;
  return (
    <figure className={cn("my-6", className)}>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="block w-full cursor-zoom-in overflow-hidden rounded-xl border bg-muted/40 shadow-xs transition-[border-color] duration-150 hover:border-brand/40"
        aria-label={text ? `Open the picture: ${text}` : "Open the picture"}
      >
        {/* eslint-disable-next-line @next/next/no-img-element -- served by the API, sizes known */}
        <img
          src={imageSrc(picture.url)}
          alt={text ?? ""}
          width={picture.width || undefined}
          height={picture.height || undefined}
          loading="lazy"
          className="mx-auto h-auto max-h-[28rem] w-auto max-w-full object-contain"
        />
      </button>
      {text && <figcaption className="mt-2 font-sans text-sm text-muted-foreground">{text}</figcaption>}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-[min(92vw,1100px)] p-2 sm:max-w-[min(92vw,1100px)]">
          <DialogTitle className="sr-only">{text || "Picture"}</DialogTitle>
          {/* eslint-disable-next-line @next/next/no-img-element -- full size, from the API */}
          <img src={imageSrc(picture.url)} alt={text ?? ""} className="max-h-[82vh] w-full rounded-lg object-contain" />
          {text && <p className="px-2 pb-1 text-sm text-muted-foreground">{text}</p>}
        </DialogContent>
      </Dialog>
    </figure>
  );
}

/**
 * An item's cover, or, when it has none, a quiet panel in its first tag's color. Covers crop
 * from the top, so a document's first page shows its title. With `shape`, the cover takes
 * the classes for its picture's shape once it has loaded (a PDF page is tall, a video wide).
 */
export function Cover({
  item,
  className,
  shape,
}: {
  item: Pick<Item, "cover_url" | "source_type" | "tags" | "title">;
  className?: string;
  shape?: { tall: string; wide: string };
}) {
  const [tall, setTall] = useState<boolean | null>(null);
  if (item.cover_url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- served by the API
      <img
        src={imageSrc(item.cover_url)}
        alt=""
        loading="lazy"
        onLoad={(e) => setTall(e.currentTarget.naturalHeight > e.currentTarget.naturalWidth)}
        className={cn(
          // White diagrams and page scans glare on the dark page; dim them a little there.
          "block bg-muted object-cover object-top dark:brightness-[0.85]",
          shape && (tall === null ? "invisible " + shape.wide : tall ? shape.tall : shape.wide),
          className,
        )}
      />
    );
  }
  const color = item.tags[0]?.color ?? "#8d8d86";
  return (
    <div
      aria-hidden
      className={cn("grid place-items-center", className)}
      style={{ background: `linear-gradient(135deg, color-mix(in oklab, ${color} 22%, var(--card)), color-mix(in oklab, ${color} 8%, var(--card)))` }}
    >
      <SourceIcon type={item.source_type} className="size-6 opacity-60" />
    </div>
  );
}

/** The pictures a note's text refers to. */
export function pictureIds(text: string) {
  return [...text.matchAll(IMAGE_TOKEN)].map((m) => ({ alt: m[1], id: Number(m[2]) }));
}

/**
 * Adding pictures to a note: a button, pasting, or dropping files. Each upload is put in the
 * text as ![name](image:ID) where the caret is.
 */
export function usePictureInsert({
  itemId,
  textarea,
  value,
  onChange,
}: {
  itemId?: number;
  textarea: React.RefObject<HTMLTextAreaElement | null>;
  value: string;
  onChange: (next: string) => void;
}) {
  const [uploading, setUploading] = useState(0);

  async function add(files: File[]) {
    const pictures = files.filter((f) => f.type.startsWith("image/"));
    if (!pictures.length) return;
    setUploading((n) => n + pictures.length);
    const tokens: string[] = [];
    for (const file of pictures) {
      try {
        const name = file.name.replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
        const alt = /^(image|screenshot|img|photo)\b/i.test(name) || !name ? "" : name.slice(0, 80);
        const made = await api.uploadImage(file, itemId, alt || undefined);
        tokens.push(`![${alt}](image:${made.id})`);
      } catch (err) {
        toast.error((err as Error).message);
      } finally {
        setUploading((n) => n - 1);
      }
    }
    if (!tokens.length) return;
    const el = textarea.current;
    const at = el?.selectionStart ?? value.length;
    const before = value.slice(0, at);
    const after = value.slice(at);
    const lead = before && !before.endsWith("\n\n") ? (before.endsWith("\n") ? "\n" : "\n\n") : "";
    const insert = lead + tokens.join("\n\n") + "\n\n";
    onChange(before + insert + after.replace(/^\n+/, ""));
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(at + insert.length, at + insert.length);
    });
  }

  const handlers = {
    onPaste: (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const files = [...e.clipboardData.files];
      if (files.some((f) => f.type.startsWith("image/"))) {
        e.preventDefault();
        add(files);
      }
    },
    onDrop: (e: React.DragEvent<HTMLTextAreaElement>) => {
      const files = [...e.dataTransfer.files];
      if (files.some((f) => f.type.startsWith("image/"))) {
        e.preventDefault();
        add(files);
      }
    },
  };
  return { add, uploading: uploading > 0, handlers };
}

export function PictureButton({ onFiles, busy, className }: { onFiles: (files: File[]) => void; busy?: boolean; className?: string }) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button
        type="button"
        onClick={() => input.current?.click()}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs text-muted-foreground transition-[color,border-color,transform] duration-150 hover:border-brand/50 hover:text-foreground active:scale-[0.97]",
          className,
        )}
      >
        {busy ? <Loader2 className="size-3.5 animate-spin motion-reduce:animate-none" aria-hidden /> : <ImagePlus className="size-3.5" aria-hidden />}
        {busy ? "Adding…" : "Add picture"}
      </button>
      <input
        ref={input}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={(e) => {
          onFiles([...(e.target.files ?? [])]);
          e.target.value = "";
        }}
      />
    </>
  );
}

/** Thumbnails of the pictures in a note, each removable (which takes its reference out). */
export function NotePictures({ text, onRemove }: { text: string; onRemove?: (id: number) => void }) {
  const pictures = pictureIds(text);
  if (!pictures.length) return null;
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Pictures in this note">
      {pictures.map((p) => (
        <li key={p.id} className="group relative">
          {/* eslint-disable-next-line @next/next/no-img-element -- served by the API */}
          <img src={imageSrc(`/images/${p.id}`)} alt={p.alt} className="size-20 rounded-lg border bg-muted object-cover shadow-xs" />
          {onRemove && (
            <button
              type="button"
              onClick={() => onRemove(p.id)}
              aria-label={`Remove picture${p.alt ? ` ${p.alt}` : ""}`}
              className="absolute -top-1.5 -right-1.5 grid size-5 place-items-center rounded-full border bg-background text-muted-foreground opacity-0 shadow-xs transition-opacity group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100"
            >
              <X className="size-3" />
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

/** A note's text with one picture's reference taken out. */
export function withoutPicture(text: string, id: number) {
  return text
    .replace(new RegExp(`!\\[[^\\]\\n]*\\]\\(image:${id}\\)`, "g"), "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** A note with its pictures shown where they were added. */
export function NoteView({ text, className }: { text: string; className?: string }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(IMAGE_TOKEN)) {
    const before = text.slice(last, match.index).trim();
    if (before) parts.push(<Paragraphs key={`t${last}`} text={before} />);
    parts.push(<Figure key={`i${match.index}`} picture={{ url: `/images/${match[2]}`, alt: match[1] || null, width: 0, height: 0 }} className="my-3" />);
    last = match.index + match[0].length;
  }
  const rest = text.slice(last).trim();
  if (rest) parts.push(<Paragraphs key={`t${last}`} text={rest} />);
  return <div className={className}>{parts}</div>;
}

function Paragraphs({ text }: { text: string }) {
  return (
    <>
      {text.split(/\n\s*\n/).map((p, i) => (
        <p key={i} className="mb-3 whitespace-pre-wrap last:mb-0">
          {p}
        </p>
      ))}
    </>
  );
}
