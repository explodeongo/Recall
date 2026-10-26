"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, KeyRound, Loader2, Plug, Trash2 } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";
import { timeAgo } from "@/components/ItemBits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const CLIENTS = [
  { id: "claude-code", label: "Claude Code" },
  { id: "json", label: "Claude Desktop, Cursor, others" },
] as const;

/** Connect AI assistants to the library over MCP: make a token, copy the setup. */
export function ConnectAssistants() {
  const queryClient = useQueryClient();
  const nameId = useId();
  const config = useQuery({ queryKey: ["auth-config"], queryFn: api.authConfig, staleTime: Infinity });
  const tokens = useQuery({ queryKey: ["api-tokens"], queryFn: api.apiTokens });
  const [name, setName] = useState("");
  // The token just made: shown once, here, until the page is left.
  const [fresh, setFresh] = useState<string | null>(null);
  const [client, setClient] = useState<(typeof CLIENTS)[number]["id"]>("claude-code");

  const create = useMutation({
    mutationFn: () => api.createApiToken(name.trim() || "AI assistant"),
    onSuccess: (made) => {
      setFresh(made.token);
      setName("");
      queryClient.invalidateQueries({ queryKey: ["api-tokens"] });
    },
    onError: (err) => toast.error(err.message),
  });
  const revoke = useMutation({
    mutationFn: (id: number) => api.revokeApiToken(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["api-tokens"] });
      toast.success("Token revoked. Anything using it is disconnected.");
    },
    onError: (err) => toast.error(err.message),
  });

  const url = config.data?.mcp_url ?? "http://localhost:8000/mcp";
  const token = fresh ?? "<your token>";
  const snippet =
    client === "claude-code"
      ? `claude mcp add --transport http recall ${url} --header "Authorization: Bearer ${token}"`
      : JSON.stringify({ mcpServers: { recall: { type: "http", url, headers: { Authorization: `Bearer ${token}` } } } }, null, 2);

  return (
    <section aria-labelledby="assistants-title" className="space-y-4">
      <div>
        <h2 id="assistants-title" className="flex items-center gap-2 font-heading text-2xl font-medium">
          <Plug className="size-5 text-brand" aria-hidden /> Connect AI assistants
        </h2>
        <p className="mt-1 text-sm text-pretty text-muted-foreground">
          Let Claude, Cursor or any MCP app use your library: search it, ask it with citations, read what you saved, and save new
          things when you ask. Each app gets its own token, which you can revoke any time.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
        className="flex gap-2"
      >
        <label htmlFor={nameId} className="sr-only">
          Token name
        </label>
        <Input id={nameId} value={name} onChange={(e) => setName(e.target.value)} placeholder="Name it, e.g. Claude on my laptop" maxLength={80} />
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? <Loader2 className="animate-spin" /> : <KeyRound />} Make a token
        </Button>
      </form>

      {fresh && (
        <div className="animate-enter space-y-2 rounded-xl border border-brand/40 bg-brand-soft/40 p-4" role="status">
          <p className="text-sm font-medium">Copy this token now. Recall won&apos;t show it again.</p>
          <CopyField value={fresh} label="Copy token" mono />
        </div>
      )}

      <div className="space-y-2 rounded-xl border bg-card shadow-xs p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium">Set it up</p>
          <div role="tablist" aria-label="App" className="flex rounded-full border p-0.5 text-xs">
            {CLIENTS.map((c) => (
              <button
                key={c.id}
                role="tab"
                aria-selected={client === c.id}
                onClick={() => setClient(c.id)}
                className={cn(
                  "rounded-full px-2.5 py-0.5 transition-colors duration-150",
                  client === c.id ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
                )}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
        <p className="text-xs text-muted-foreground">
          {client === "claude-code" ? "Run this in a terminal." : "Add this to the app's MCP settings (mcp.json or claude_desktop_config.json)."}
          {!fresh && " Make a token first; it fills in here."}
        </p>
        <CopyField value={snippet} label="Copy setup" mono multiline={client === "json"} />
      </div>

      {tokens.data && tokens.data.length > 0 && (
        <ul className="divide-y rounded-xl border" aria-label="Your tokens">
          {tokens.data.map((t) => (
            <li key={t.id} className="flex items-center gap-3 px-4 py-3 text-sm">
              <KeyRound className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{t.name}</p>
                <p className="text-xs text-muted-foreground">
                  <code className="font-mono">{t.prefix}…</code> · made {timeAgo(t.created_at)} ·{" "}
                  {t.last_used_at ? `last used ${timeAgo(t.last_used_at)}` : "never used"}
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={() => revoke.mutate(t.id)}
                disabled={revoke.isPending}
                aria-label={`Revoke ${t.name}`}
                className="text-muted-foreground hover:text-destructive"
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function CopyField({ value, label, mono, multiline }: { value: string; label: string; mono?: boolean; multiline?: boolean }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-start gap-2 rounded-lg border bg-background p-2">
      <pre className={cn("min-w-0 flex-1 overflow-x-auto px-1 py-0.5 text-xs leading-relaxed", mono && "font-mono", !multiline && "whitespace-pre-wrap break-all")}>{value}</pre>
      <Button
        type="button"
        variant="ghost"
        size="icon-sm"
        aria-label={copied ? "Copied" : label}
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          } catch {
            toast.error("Couldn't copy. Select the text and copy it instead.");
          }
        }}
      >
        <span className="relative grid size-4 place-items-center">
          <Copy className={cn("icon-swap absolute", copied && "scale-50 opacity-0 blur-[2px]")} />
          <Check className={cn("icon-swap absolute text-emerald-600 dark:text-emerald-400", !copied && "scale-50 opacity-0 blur-[2px]")} />
        </span>
      </Button>
    </div>
  );
}
