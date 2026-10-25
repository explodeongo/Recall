"use client";

import { Library, MessageSquareText, Moon, Plus, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const links = [
  { href: "/", label: "Library", icon: Library },
  { href: "/ask", label: "Ask", icon: MessageSquareText },
  { href: "/add", label: "Add", icon: Plus },
];

export function Nav() {
  const pathname = usePathname();
  const { resolvedTheme, setTheme } = useTheme();
  const isActive = (href: string) => (href === "/" ? pathname === "/" || pathname.startsWith("/items") : pathname.startsWith(href));

  return (
    <header className="sticky top-0 z-40 border-b bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <nav className="mx-auto flex h-14 max-w-4xl items-center gap-1 px-4 sm:px-6" aria-label="Main">
        <Link href="/" className="mr-4 flex items-center gap-2" aria-label="Recall home">
          <span className="grid size-7 place-items-center rounded-md bg-brand font-heading text-[17px] leading-none font-semibold text-brand-foreground">
            R
          </span>
          <span className="font-heading text-xl font-semibold tracking-tight">Recall</span>
        </Link>
        {links.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={isActive(href) ? "page" : undefined}
            className={cn(
              "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
              isActive(href) && "bg-muted font-medium text-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden />
            <span className="hidden sm:inline">{label}</span>
          </Link>
        ))}
        <Button
          variant="ghost"
          size="icon"
          className="ml-auto"
          aria-label="Toggle dark mode"
          onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
        >
          <Sun className="hidden size-4 dark:block" />
          <Moon className="size-4 dark:hidden" />
        </Button>
      </nav>
    </header>
  );
}
