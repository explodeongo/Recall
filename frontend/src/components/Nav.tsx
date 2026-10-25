import Link from "next/link";

const links = [
  { href: "/", label: "Library" },
  { href: "/add", label: "Add" },
  { href: "/ask", label: "Ask" },
];

export function Nav() {
  return (
    <header className="border-b border-zinc-200 dark:border-zinc-800">
      <nav className="mx-auto flex max-w-4xl items-center gap-6 px-4 py-3">
        <Link href="/" className="text-lg font-semibold tracking-tight">
          Recall
        </Link>
        {links.map((l) => (
          <Link key={l.href} href={l.href} className="text-sm text-zinc-600 hover:text-zinc-950 dark:text-zinc-400 dark:hover:text-zinc-50">
            {l.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
