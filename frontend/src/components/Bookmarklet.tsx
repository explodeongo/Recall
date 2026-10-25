"use client";

import { Bookmark } from "lucide-react";
import { useEffect, useRef } from "react";

/**
 * A "Save to Recall" button to drag to the bookmarks bar. Clicking it on any page opens a
 * small window that saves that page. React won't render a javascript: link, so the href is
 * set after mounting.
 */
export function Bookmarklet() {
  const link = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    const origin = window.location.origin;
    const code = `javascript:(function(){window.open('${origin}/save?url='+encodeURIComponent(location.href)+'&title='+encodeURIComponent(document.title),'recall-save','width=440,height=440');})();`;
    link.current?.setAttribute("href", code);
  }, []);

  return (
    <section aria-labelledby="bookmarklet-title" className="space-y-3 rounded-2xl border bg-card p-6">
      <h2 id="bookmarklet-title" className="font-heading text-xl font-medium">
        Save from any page in one click
      </h2>
      <p className="text-sm text-muted-foreground">
        Drag this button to your browser&apos;s bookmarks bar. On any article, PDF or video, click it and the page is saved to
        Recall. On your phone, install Recall from the browser menu (&ldquo;Add to Home screen&rdquo;) and it appears in the
        Share menu.
      </p>
      <a
        ref={link}
        draggable
        onClick={(e) => e.preventDefault() /* it's meant to be dragged, not clicked here */}
        className="inline-flex cursor-grab items-center gap-2 rounded-lg bg-brand px-3 py-2 text-sm font-medium text-brand-foreground shadow-sm active:cursor-grabbing"
      >
        <Bookmark className="size-4" aria-hidden /> Save to Recall
      </a>
    </section>
  );
}
