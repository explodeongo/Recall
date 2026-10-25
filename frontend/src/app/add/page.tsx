import type { Metadata } from "next";
import { AddSources } from "@/components/AddSources";

export const metadata: Metadata = { title: "Add" };

export default function AddPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <header>
        <h1 className="text-balance font-heading text-4xl font-medium">Add to your library</h1>
        <p className="mt-2 text-muted-foreground">
          Save a PDF or a link to an article. Recall reads it, writes a summary and tags it for you.
        </p>
      </header>
      <AddSources />
    </div>
  );
}
