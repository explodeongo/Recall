import type { Metadata } from "next";
import { AddSources } from "@/components/AddSources";
import { Bookmarklet } from "@/components/Bookmarklet";

export const metadata: Metadata = { title: "Add" };

export default function AddPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <header>
        <h1 className="text-balance font-heading text-4xl font-medium">Add to your library</h1>
        <p className="mt-2 text-muted-foreground">
          Save files, links, videos or your own notes. Recall reads them, writes a summary and tags them for you.
        </p>
      </header>
      <AddSources />
      <Bookmarklet />
    </div>
  );
}
