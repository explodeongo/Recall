"use client";

import { Pause, Play, Square, Volume2 } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Read aloud, with the browser's own voices (speechSynthesis): free, private, nothing to
 * install. Text is spoken a sentence or two at a time, because some browsers stop partway
 * through one long utterance. One thing plays at a time, from any page; the bar at the top
 * right pauses, changes speed or stops it.
 */

interface Track {
  id: string;
  title: string;
  text: string;
}

interface Speech {
  supported: boolean;
  track: Track | null;
  playing: boolean;
  progress: number; // 0..1
  rate: number;
  play: (track: Track) => void;
  toggle: () => void;
  stop: () => void;
  cycleRate: () => void;
}

const SpeechContext = createContext<Speech | null>(null);
const RATES = [1, 1.25, 1.5, 2, 0.85];

/** What reads well aloud: no citation markers, picture references, markdown or bare links. */
export function speakable(text: string) {
  return text
    .replace(/!\[([^\]\n]*)\]\(image:\d+\)/g, "$1")
    .replace(/\s*\[\d+(?:\s*,\s*\d+)*\]/g, "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/^\s*[-*•]\s+/gm, "")
    .replace(/[_^]\{([^}]*)\}/g, " $1")
    .replace(/\s+\n/g, "\n")
    .trim();
}

/** Sentences, grouped up to about 220 characters. */
function pieces(text: string) {
  const sentences = text.match(/[^.!?\n]+(?:[.!?]+["')\]]?|\n|$)/g) ?? [text];
  const out: string[] = [];
  let current = "";
  for (const raw of sentences) {
    const s = raw.trim();
    if (!s) continue;
    if ((current + " " + s).length > 220 && current) {
      out.push(current);
      current = s;
    } else current = current ? `${current} ${s}` : s;
  }
  if (current) out.push(current);
  return out;
}

/** The most natural-sounding English voice the device has. */
function bestVoice(): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith("en"));
  const prefer = [/natural/i, /neural/i, /premium/i, /enhanced/i, /samantha/i, /google (uk|us) english/i, /daniel/i];
  for (const pattern of prefer) {
    const found = voices.find((v) => pattern.test(v.name));
    if (found) return found;
  }
  return voices.find((v) => v.default) ?? voices[0];
}

export function SpeechProvider({ children }: { children: React.ReactNode }) {
  const [supported, setSupported] = useState(false);
  const [track, setTrack] = useState<Track | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [rate, setRate] = useState(1);
  const queue = useRef<string[]>([]);
  const index = useRef(0);
  const session = useRef(0); // bumps on every new play or stop, so stale callbacks do nothing
  const rateRef = useRef(1);

  useEffect(() => {
    setSupported(typeof window !== "undefined" && "speechSynthesis" in window);
    try {
      const saved = Number(localStorage.getItem("recall-speech-rate"));
      if (RATES.includes(saved)) {
        setRate(saved);
        rateRef.current = saved;
      }
    } catch {}
    window.speechSynthesis?.getVoices(); // starts loading them early
    return () => window.speechSynthesis?.cancel();
  }, []);

  const speakFrom = useCallback((at: number) => {
    const synth = window.speechSynthesis;
    const id = ++session.current;
    synth.cancel();
    const next = (i: number) => {
      if (id !== session.current) return;
      if (i >= queue.current.length) {
        setPlaying(false);
        setTrack(null);
        setProgress(0);
        return;
      }
      index.current = i;
      setProgress(i / queue.current.length);
      const utterance = new SpeechSynthesisUtterance(queue.current[i]);
      const voice = bestVoice();
      if (voice) utterance.voice = voice;
      utterance.lang = voice?.lang ?? "en-US";
      utterance.rate = rateRef.current;
      utterance.onend = () => next(i + 1);
      utterance.onerror = (e) => {
        if (e.error !== "interrupted" && e.error !== "canceled") next(i + 1);
      };
      synth.speak(utterance);
    };
    next(at);
    setPlaying(true);
  }, []);

  const play = useCallback(
    (t: Track) => {
      queue.current = pieces(speakable(t.text));
      if (!queue.current.length) return;
      setTrack(t);
      speakFrom(0);
    },
    [speakFrom],
  );

  const stop = useCallback(() => {
    session.current++;
    window.speechSynthesis?.cancel();
    setPlaying(false);
    setTrack(null);
    setProgress(0);
  }, []);

  // Pause by stopping and resume from the same piece: speechSynthesis.pause() is unreliable.
  const toggle = useCallback(() => {
    if (!track) return;
    if (playing) {
      session.current++;
      window.speechSynthesis.cancel();
      setPlaying(false);
    } else speakFrom(index.current);
  }, [track, playing, speakFrom]);

  const cycleRate = useCallback(() => {
    const next = RATES[(RATES.indexOf(rateRef.current) + 1) % RATES.length];
    rateRef.current = next;
    setRate(next);
    try {
      localStorage.setItem("recall-speech-rate", String(next));
    } catch {}
    if (playing) speakFrom(index.current); // the new speed starts with this piece
  }, [playing, speakFrom]);

  const value = useMemo(
    () => ({ supported, track, playing, progress, rate, play, toggle, stop, cycleRate }),
    [supported, track, playing, progress, rate, play, toggle, stop, cycleRate],
  );
  return (
    <SpeechContext.Provider value={value}>
      {children}
      <NowPlaying />
    </SpeechContext.Provider>
  );
}

export function useSpeech() {
  const speech = useContext(SpeechContext);
  if (!speech) throw new Error("useSpeech needs a SpeechProvider");
  return speech;
}

/** Play or pause reading `text` aloud. Hidden where the browser can't speak. */
export function ListenButton({
  id,
  title,
  text,
  label = "Listen",
  className,
}: {
  id: string;
  title: string;
  text: string;
  label?: string;
  className?: string;
}) {
  const speech = useSpeech();
  if (!speech.supported) return null;
  const current = speech.track?.id === id;
  return (
    <button
      type="button"
      onClick={() => (current ? speech.toggle() : speech.play({ id, title, text }))}
      aria-pressed={current && speech.playing}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-[color,border-color,background-color,transform] duration-150 active:scale-[0.97]",
        current ? "border-brand/50 bg-brand-soft text-brand" : "text-muted-foreground hover:border-brand/50 hover:text-foreground",
        className,
      )}
    >
      {current && speech.playing ? <Pause className="size-3.5" aria-hidden /> : <Volume2 className="size-3.5" aria-hidden />}
      {current ? (speech.playing ? "Pause" : "Resume") : label}
    </button>
  );
}

function NowPlaying() {
  const speech = useContext(SpeechContext)!;
  if (!speech.track) return null;
  return (
    <div
      role="region"
      aria-label="Reading aloud"
      className="fixed top-16 right-4 z-50 flex w-72 max-w-[calc(100vw-2rem)] animate-enter items-center gap-2 overflow-hidden rounded-xl border bg-popover p-2 pl-3 text-popover-foreground shadow-lg"
    >
      <span className="absolute inset-x-0 bottom-0 h-0.5 bg-brand/15" aria-hidden>
        <span className="block h-full bg-brand transition-[width] duration-500 ease-(--ease-out)" style={{ width: `${Math.round(speech.progress * 100)}%` }} />
      </span>
      <Volume2 className={cn("size-4 shrink-0 text-brand", speech.playing && "animate-pulse motion-reduce:animate-none")} aria-hidden />
      <span className="min-w-0 flex-1 truncate text-sm">{speech.track.title}</span>
      <button
        type="button"
        onClick={speech.cycleRate}
        aria-label={`Speed ${speech.rate}×, change`}
        className="rounded-md px-1.5 py-0.5 text-xs text-muted-foreground tabular-nums hover:bg-muted hover:text-foreground"
      >
        {speech.rate}×
      </button>
      <button type="button" onClick={speech.toggle} aria-label={speech.playing ? "Pause" : "Resume"} className="grid size-7 place-items-center rounded-md hover:bg-muted">
        {speech.playing ? <Pause className="size-4" /> : <Play className="size-4" />}
      </button>
      <button type="button" onClick={speech.stop} aria-label="Stop reading" className="grid size-7 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground">
        <Square className="size-3.5 fill-current" />
      </button>
    </div>
  );
}
