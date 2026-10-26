"use client";

import { useQuery } from "@tanstack/react-query";
import { Highlighter, Layers, Library, LogOut, MessageSquareText, Moon, Network, Plus, Search, Settings, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { openSearch } from "@/components/SearchPalette";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Library", icon: Library },
  { href: "/ask", label: "Ask", icon: MessageSquareText },
  { href: "/review", label: "Review", icon: Layers },
  { href: "/graph", label: "Graph", icon: Network },
  { href: "/add", label: "Add", icon: Plus },
];

export function Nav() {
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();
  const authPage = pathname === "/login" || pathname === "/signup";
  const stats = useQuery({ queryKey: ["review-stats"], queryFn: api.reviewStats, enabled: !authPage, refetchInterval: 60_000 });
  const isActive = (href: string) => (href === "/" ? pathname === "/" || pathname.startsWith("/items") : pathname.startsWith(href));

  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <nav className="mx-auto flex h-14 max-w-6xl items-center gap-1 px-4 sm:px-6" aria-label="Main">
        <Link href="/" className="mr-1 flex items-center gap-2 sm:mr-4" aria-label="Recall home">
          <span className="grid size-7 place-items-center rounded-md bg-brand font-heading text-[17px] leading-none font-semibold text-brand-foreground">
            R
          </span>
          <span className="hidden font-heading text-xl font-semibold tracking-tight sm:inline">Recall</span>
        </Link>
        {!authPage && links.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={isActive(href) ? "page" : undefined}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:px-2.5",
              isActive(href) && "bg-brand-soft font-medium text-brand hover:bg-brand-soft hover:text-brand",
            )}
          >
            <Icon className="size-4" aria-hidden />
            <span className="hidden sm:inline">{label}</span>
            {href === "/review" && !!stats.data?.due && (
              <span className="min-w-4 rounded-full bg-brand px-1 text-center text-[11px] leading-4 font-semibold text-brand-foreground tabular-nums" aria-label={`${stats.data.due} cards due`}>
                {stats.data.due > 99 ? "99+" : stats.data.due}
              </span>
            )}
          </Link>
        ))}
        {!authPage && (
          <button
            onClick={openSearch}
            className="ml-auto flex h-8 items-center gap-2 rounded-md border bg-card shadow-xs px-2.5 text-sm text-muted-foreground transition-colors duration-150 hover:text-foreground sm:w-56"
            aria-label="Search your library"
          >
            <Search className="size-4" aria-hidden />
            <span className="hidden sm:inline">Search</span>
            <kbd className="ml-auto hidden rounded border bg-muted px-1.5 font-sans text-[11px] sm:inline">⌘K</kbd>
          </button>
        )}
        <Button
          variant="ghost"
          size="icon"
          // On phones there isn't room; the account menu has it there.
          className={authPage ? "ml-auto" : "hidden sm:inline-flex"}
          aria-label="Toggle dark mode"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        >
          <Sun className="hidden size-4 dark:block" />
          <Moon className="size-4 dark:hidden" />
        </Button>
        {!authPage && <AccountMenu />}
      </nav>
    </header>
  );
}

function AccountMenu() {
  const router = useRouter();
  const { resolvedTheme, setTheme } = useTheme();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity });
  if (!me.data) return null;
  const initial = (me.data.name || me.data.email).trim()[0]?.toUpperCase() ?? "?";

  async function logout() {
    try {
      await api.logout();
    } finally {
      window.location.assign("/login");
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={<Button variant="ghost" size="icon" aria-label={`Account: ${me.data.email}`} />}
      >
        <span className="grid size-7 place-items-center rounded-full bg-brand-soft text-xs font-semibold text-brand">{initial}</span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          {me.data.name && <span className="block truncate text-sm font-medium text-foreground">{me.data.name}</span>}
          <span className="block truncate text-xs text-muted-foreground">{me.data.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={() => router.push("/highlights")}>
          <Highlighter /> Highlights
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => router.push("/settings")}>
          <Settings /> Settings and export
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
          {resolvedTheme === "dark" ? <Sun /> : <Moon />} {resolvedTheme === "dark" ? "Light mode" : "Dark mode"}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={logout}>
          <LogOut /> Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
