"use client";

import { useEffect, useRef, useState } from "react";
import { PRESET_COLORS, hexToRgb, hsvToHex, hsvToRgb, rgbToHex, rgbToHsv, type HSV } from "@/lib/color";
import { cn } from "@/lib/utils";

/**
 * An RGB color wheel: the angle picks the hue, the distance from the middle the saturation,
 * and the slider below the brightness. The exact color can also be typed as hex or R, G, B.
 *
 * The wheel is plain CSS: a conic gradient of hues, a radial gradient from white in the middle,
 * and a black layer whose opacity is 1 − brightness. Gradients mix in sRGB, which is exactly
 * how HSV mixes, so the color under the thumb is the color you get.
 */
export function ColorWheel({ value, onChange }: { value: string; onChange: (hex: string) => void }) {
  // Kept as HSV, so the hue isn't lost when the color goes grey or black.
  const [hsv, setHsv] = useState<HSV>(() => rgbToHsv(hexToRgb(value) ?? { r: 99, g: 102, b: 241 }));
  const hex = hsvToHex(hsv);
  useEffect(() => {
    if (value.toLowerCase() !== hex) {
      const rgb = hexToRgb(value);
      if (rgb) setHsv(rgbToHsv(rgb));
    }
    // Only outside changes to `value` should move the wheel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  function set(next: HSV) {
    setHsv(next);
    onChange(hsvToHex(next));
  }

  const wheel = useRef<HTMLDivElement>(null);
  function pick(e: React.PointerEvent) {
    const box = wheel.current!.getBoundingClientRect();
    const radius = box.width / 2;
    const dx = e.clientX - box.left - radius;
    const dy = e.clientY - box.top - radius;
    const h = ((Math.atan2(dx, -dy) * 180) / Math.PI + 360) % 360;
    const s = Math.min(1, Math.hypot(dx, dy) / radius);
    set({ ...hsv, h, s, v: hsv.v < 0.15 ? 1 : hsv.v }); // picking from the wheel while it's black would show nothing
  }

  function onKey(e: React.KeyboardEvent) {
    const step = e.shiftKey ? 15 : 5;
    const moves: Record<string, Partial<HSV>> = {
      ArrowLeft: { h: (hsv.h - step + 360) % 360 },
      ArrowRight: { h: (hsv.h + step) % 360 },
      ArrowUp: { s: Math.min(1, hsv.s + step / 100) },
      ArrowDown: { s: Math.max(0, hsv.s - step / 100) },
    };
    if (moves[e.key]) {
      e.preventDefault();
      set({ ...hsv, ...moves[e.key] });
    }
  }

  const angle = (hsv.h * Math.PI) / 180;
  const pure = hsvToHex({ h: hsv.h, s: hsv.s, v: 1 });
  const rgb = hsvToRgb(hsv);

  return (
    <div className="w-56 space-y-3 p-2" style={{ "--hue": pure, "--swatch": hex } as React.CSSProperties}>
      <div
        ref={wheel}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          pick(e);
        }}
        onPointerMove={(e) => e.buttons === 1 && pick(e)}
        className="relative mx-auto aspect-square w-full cursor-crosshair touch-none rounded-full shadow-[inset_0_0_0_1px_rgb(0_0_0/0.12)]"
        style={{
          background:
            "radial-gradient(closest-side, #fff, rgb(255 255 255 / 0)), conic-gradient(#f00, #ff0, #0f0, #0ff, #00f, #f0f, #f00)",
        }}
      >
        <div className="pointer-events-none absolute inset-0 rounded-full bg-black" style={{ opacity: 1 - hsv.v }} />
        <div
          role="slider"
          tabIndex={0}
          aria-label="Hue and saturation"
          aria-valuemin={0}
          aria-valuemax={359}
          aria-valuenow={Math.round(hsv.h)}
          aria-valuetext={`Hue ${Math.round(hsv.h)} degrees, saturation ${Math.round(hsv.s * 100)}%`}
          onKeyDown={onKey}
          className="absolute size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-[0_0_0_1px_rgb(0_0_0/0.3),0_1px_4px_rgb(0_0_0/0.35)] outline-offset-2"
          style={{
            left: `${50 + Math.sin(angle) * hsv.s * 50}%`,
            top: `${50 - Math.cos(angle) * hsv.s * 50}%`,
            background: hex,
          }}
        />
      </div>

      <label className="block">
        <span className="sr-only">Brightness</span>
        <input
          type="range"
          min={0}
          max={100}
          value={Math.round(hsv.v * 100)}
          onChange={(e) => set({ ...hsv, v: Number(e.target.value) / 100 })}
          className="color-range w-full"
        />
      </label>

      <div className="grid grid-cols-[1.75rem_1fr_1fr_1fr] items-end gap-1.5">
        <span className="size-7 rounded-md shadow-[inset_0_0_0_1px_rgb(0_0_0/0.15)]" style={{ background: hex }} aria-hidden />
        <HexInput value={hex} onChange={(next) => set(rgbToHsv(hexToRgb(next)!))} />
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {(["r", "g", "b"] as const).map((c) => (
          <label key={c} className="flex items-center gap-1.5">
            <span className="text-[10px] font-medium text-muted-foreground uppercase">{c}</span>
            <input
              type="number"
              min={0}
              max={255}
              value={Math.round(rgb[c])}
              onChange={(e) => {
                const n = Math.max(0, Math.min(255, Number(e.target.value) || 0));
                set(rgbToHsv({ ...rgb, [c]: n }));
              }}
              aria-label={{ r: "Red", g: "Green", b: "Blue" }[c]}
              className="h-7 w-full min-w-0 rounded-md border bg-background text-center text-xs tabular-nums outline-none [appearance:textfield] focus:border-brand/60 [&::-webkit-inner-spin-button]:appearance-none"
            />
          </label>
        ))}
      </div>

      <div className="grid grid-cols-10 gap-1" role="group" aria-label="Suggested colors">
        {PRESET_COLORS.map((c) => (
          <button
            key={c}
            type="button"
            onClick={() => set(rgbToHsv(hexToRgb(c)!))}
            aria-label={`Use ${c}`}
            aria-pressed={c === hex}
            className={cn(
              "aspect-square w-full rounded-full shadow-[inset_0_0_0_1px_rgb(0_0_0/0.15)] transition-transform duration-150 ease-(--ease-out) hover:scale-110 active:scale-95",
              c === hex && "ring-2 ring-foreground/70 ring-offset-1 ring-offset-popover",
            )}
            style={{ background: c }}
          />
        ))}
      </div>
    </div>
  );
}

/** A hex field that only applies a color once it's a complete one. */
function HexInput({ value, onChange }: { value: string; onChange: (hex: string) => void }) {
  const [draft, setDraft] = useState(value);
  const [focused, setFocused] = useState(false);
  const shown = focused ? draft : value;
  return (
    <label className="col-span-3 flex items-center gap-1.5">
      <span className="text-[10px] font-medium text-muted-foreground">HEX</span>
      <input
        value={shown}
        onFocus={() => {
          setDraft(value);
          setFocused(true);
        }}
        onBlur={() => setFocused(false)}
        onChange={(e) => {
          const next = e.target.value.startsWith("#") ? e.target.value : `#${e.target.value}`;
          setDraft(next);
          if (hexToRgb(next)) onChange(rgbToHex(hexToRgb(next)!));
        }}
        maxLength={7}
        spellCheck={false}
        aria-label="Hex color"
        className="h-7 w-full min-w-0 rounded-md border bg-background px-2 font-mono text-xs outline-none focus:border-brand/60"
      />
    </label>
  );
}
