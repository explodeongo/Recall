import { ImageResponse } from "next/og";
import { Mark } from "@/app/brand-mark";

const SIZES = new Set([192, 512]);

/** App icons for the install manifest, drawn from the brand mark (no image files to keep):
 * /icons/192 and /icons/512 are the rounded tile, /icons/maskable fills the square for
 * Android to shape. */
export async function GET(_request: Request, { params }: { params: Promise<{ size: string }> }) {
  const name = (await params).size;
  if (name === "maskable") return new ImageResponse(<Mark size={512} bleed />, { width: 512, height: 512 });
  const size = Number(name);
  if (!SIZES.has(size)) return new Response("Not found", { status: 404 });
  return new ImageResponse(<Mark size={size} />, { width: size, height: size });
}
