"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { cloneElement, useId, useState } from "react";
import { DemoCard, WAKING, useSlow } from "@/components/Guest";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

/** Sign-up and log-in share one form; `mode` decides the fields and the call. */
export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const queryClient = useQueryClient();
  const next = useSearchParams().get("next");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const signup = mode === "signup";
  const config = useQuery({ queryKey: ["auth-config"], queryFn: api.authConfig });
  const waking = useSlow(config.isLoading);

  async function submit(form: FormData) {
    setBusy(true);
    setError(null);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");
    try {
      const user = signup
        ? await api.signup(email, password, String(form.get("name") ?? "") || undefined, String(form.get("invite") ?? "") || undefined)
        : await api.login(email, password);
      queryClient.setQueryData(["me"], user);
      // A full navigation, so the server sees the new session cookie on the next page.
      window.location.assign(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center">
      <div className="mb-8 text-center">
        <span className="mx-auto mb-5 grid size-10 place-items-center rounded-lg bg-brand font-heading text-2xl leading-none font-semibold text-brand-foreground">
          R
        </span>
        <h1 className="font-heading text-3xl font-medium text-balance">{signup ? "Make your library" : "Welcome back"}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          {signup ? "Save what you read. Ask it anything later." : "Log in to your Recall library."}
        </p>
        {waking && (
          <p aria-live="polite" className="mt-3 text-xs text-muted-foreground">
            {WAKING}
          </p>
        )}
      </div>

      {!signup && config.data?.guest_demo && <DemoCard hours={config.data.guest_hours} />}

      <form action={submit} className="space-y-4" noValidate={false}>
        {signup && (
          <Field label="Name" hint="Optional">
            <Input name="name" autoComplete="name" className="h-10" />
          </Field>
        )}
        <Field label="Email">
          <Input name="email" type="email" required autoComplete="email" autoFocus className="h-10" />
        </Field>
        <Field label="Password" hint={signup ? "At least 8 characters" : undefined}>
          <Input
            name="password"
            type="password"
            required
            minLength={signup ? 8 : undefined}
            autoComplete={signup ? "new-password" : "current-password"}
            className="h-10"
          />
        </Field>
        {signup && config.data?.signup_requires_code && (
          <Field label="Invite code" hint="This Recall is invite-only">
            <Input name="invite" required autoComplete="off" className="h-10" />
          </Field>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" size="lg" disabled={busy} className="h-10 w-full bg-brand text-brand-foreground hover:bg-brand/85">
          {busy && <Loader2 className="animate-spin" />}
          {signup ? "Create account" : "Log in"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        {signup ? "Already have an account? " : "New to Recall? "}
        <Link href={signup ? "/login" : "/signup"} className="text-brand underline-offset-4 hover:underline">
          {signup ? "Log in" : "Create an account"}
        </Link>
      </p>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactElement<{ id?: string; "aria-describedby"?: string }> }) {
  const id = useId();
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        {hint && (
          <span id={`${id}-hint`} className="text-xs text-muted-foreground">
            {hint}
          </span>
        )}
      </div>
      {cloneElement(children, { id, "aria-describedby": hint ? `${id}-hint` : undefined })}
    </div>
  );
}
