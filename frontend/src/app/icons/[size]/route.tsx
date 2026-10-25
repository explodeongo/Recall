import { ImageResponse } from "next/og";
import { Mark } from "@/app/brand-mark";

const SIZES = new Set([192, 512]);

/** App icons for the install manifest, drawn from the brand mark (no image files to keep). */
export async function GET(_request: Request, { params }: { params: Promise<{ size: string }> }) {
  const size = Number((await params).size);
  if (!SIZES.has(size)) return new Response("Not found", { status: 404 });
  return new ImageResponse(<Mark size={size} padding={size * 0.12} />, { width: size, height: size });
}
