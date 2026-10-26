import { ImageResponse } from "next/og";
import { Mark } from "@/app/brand-mark";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

// iOS rounds the corners itself, so the tile fills the square.
export default function AppleIcon() {
  return new ImageResponse(<Mark size={180} bleed />, size);
}
