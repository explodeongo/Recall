"use client";

import { useQuery } from "@tanstack/react-query";
import { Download, Loader2 } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConnectAssistants } from "@/components/ConnectAssistants";
import { API_URL, api } from "@/lib/api";

export default function SettingsPage() {
  const me = useQuery({ queryKey: ["me"], queryFn: api.me });
  return (
    <div className="mx-auto max-w-2xl space-y-12">
      <header>
        <h1 className="font-heading text-4xl font-medium">Settings</h1>
        {me.data && (
          <p className="mt-2 text-muted-foreground">
            Signed in as <span className="text-foreground">{me.data.email}</span>
          </p>
        )}
      </header>
      <ConnectAssistants />
      <ExportSection />
      <PasswordSection />
      {me.data && <DeleteSection email={me.data.email} />}
    </div>
  );
}

function Section({ title, children, danger }: { title: string; children: React.ReactNode; danger?: boolean }) {
  const id = useId();
  return (
    <section aria-labelledby={id} className={danger ? "space-y-4 rounded-2xl border border-destructive/30 p-6" : "space-y-4"}>
      <h2 id={id} className="font-heading text-2xl font-medium">
        {title}
      </h2>
      {children}
    </section>
  );
}

function ExportSection() {
  const [files, setFiles] = useState(false);
  return (
    <Section title="Your data">
      <p className="text-sm text-muted-foreground">
        Download everything: a Markdown file for each item (summary, your notes, highlights and flashcards), the full text Recall read,
        your chats, and a JSON copy of it all. It&apos;s yours to keep or take elsewhere.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={files} onChange={(e) => setFiles(e.target.checked)} className="size-4" />
        Include the original files you uploaded (larger download)
      </label>
      <a href={`${API_URL}/auth/export${files ? "?files=true" : ""}`} download className={buttonVariants({ variant: "outline" })}>
        <Download /> Download export
      </a>
    </Section>
  );
}

function PasswordSection() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const id = useId();
  async function submit(form: FormData) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/auth/password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: form.get("current"), new_password: form.get("new") }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "The new password needs at least 8 characters.");
      }
      toast.success("Password changed. Other devices have been signed out.");
      (document.getElementById(id) as HTMLFormElement | null)?.reset();
    } catch (err) {
      setError((err as Error).message || "Couldn't change the password.");
    } finally {
      setBusy(false);
    }
  }
  return (
    <Section title="Password">
      <form id={id} action={submit} className="max-w-sm space-y-3">
        <label className="block space-y-1.5 text-sm font-medium">
          <span>Current password</span>
          <Input name="current" type="password" required autoComplete="current-password" className="h-10" />
        </label>
        <label className="block space-y-1.5 text-sm font-medium">
          <span>New password</span>
          <Input name="new" type="password" required minLength={8} autoComplete="new-password" className="h-10" />
        </label>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" variant="outline" disabled={busy}>
          {busy && <Loader2 className="animate-spin" />} Change password
        </Button>
      </form>
    </Section>
  );
}

function DeleteSection({ email }: { email: string }) {
  const [typed, setTyped] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  async function remove() {
    setBusy(true);
    const res = await fetch(`${API_URL}/auth/delete-account`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (res.ok) {
      window.location.assign("/signup");
      return;
    }
    setBusy(false);
    toast.error(res.status === 403 ? "That password isn't right." : "Couldn't delete the account.");
  }
  return (
    <Section title="Delete account" danger>
      <p className="text-sm text-muted-foreground">
        This permanently deletes your account, every item, note, highlight, flashcard and chat, and the files you uploaded. It can&apos;t be
        undone. Download an export first if you might want any of it.
      </p>
      <div className="max-w-sm space-y-3">
        <label className="block space-y-1.5 text-sm font-medium">
          <span>
            Type <span className="font-mono text-xs">{email}</span> to confirm
          </span>
          <Input value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" className="h-10" />
        </label>
        <label className="block space-y-1.5 text-sm font-medium">
          <span>Password</span>
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" className="h-10" />
        </label>
        <Button variant="destructive" disabled={busy || typed.trim().toLowerCase() !== email || !password} onClick={remove}>
          {busy && <Loader2 className="animate-spin" />} Delete my account
        </Button>
      </div>
    </Section>
  );
}
