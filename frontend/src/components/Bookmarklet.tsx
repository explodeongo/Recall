"use client";

import { Bookmark, MousePointerClick } from "lucide-react";
import { useEffect, useRef, useState } from "react";

/**
 * A "Save to Recall" button to drag to the bookmarks bar. Clicking it on any page opens a
 * small window that saves that page. React won't render a javascript: link, so the href is
 * set after mounting. Clicked here, on Recall itself, there's nothing to save, so it says how
 * to use it instead of doing nothing.
 */
export function Bookmarklet() {
  const link = useRef<HTMLAnchorElement>(null);
  const [nudged, setNudged] = useState(false);
  const [mac, setMac] = useState(true);
  useEffect(() => {
    const origin = window.location.origin;
    const code = `javascript:(function(){window.open('${origin}/save?url='+encodeURIComponent(location.href)+'&title='+encodeURIComponent(document.title),'recall-save','width=440,height=440');})();`;
    link.current?.setAttribute("href", code);
    setMac(/Mac|iPhone|iPad/.test(navigator.platform));
  }, []);

  return (
    <section aria-labelledby="bookmarklet-title" className="space-y-3 rounded-2xl border bg-card shadow-xs p-6">
      <h2 id="bookmarklet-title" className="font-heading text-xl font-medium">
        Save from any page in one click
      </h2>
      {/* Dragging to a bookmarks bar is a desktop thing; phones get the Share menu below. */}
      <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground pointer-coarse:hidden">
        <li>
          Drag the button below to your bookmarks bar. Don&apos;t see the bar? Press{" "}
          <kbd className="rounded border bg-muted px-1 font-mono text-xs">{mac ? "⌘ ⇧ B" : "Ctrl Shift B"}</kbd>.
        </li>
        <li>On any article, PDF or video, click it. A small window saves the page and closes itself.</li>
      </ol>
      <div className="flex flex-wrap items-center gap-3 pointer-coarse:hidden">
        <a
          ref={link}
          draggable
          onClick={(e) => {
            e.preventDefault(); // on Recall itself there's no page to save
            setNudged(true);
          }}
          className="inline-flex cursor-grab items-center gap-2 rounded-lg border border-brand/30 bg-brand-soft px-3 py-2 text-sm font-medium text-brand shadow-xs active:cursor-grabbing"
        >
          <Bookmark className="size-4" aria-hidden /> Save to Recall
        </a>
        {nudged && (
          <p role="status" className="animate-enter flex items-center gap-1.5 text-sm text-foreground">
            <MousePointerClick className="size-4 text-brand" aria-hidden />
            Drag it to your bookmarks bar, then click it on the page you want to save.
          </p>
        )}
      </div>
      <p className="text-sm text-muted-foreground">
        On an Android phone, install Recall from Chrome&apos;s menu (&ldquo;Add to Home screen&rdquo;) and it shows up in
        the Share menu. On an iPhone, copy the link and paste it under Links above.
      </p>
    </section>
  );
}
