import type { NextConfig } from "next";

// The browser talks to the API through this app's own /api path, so the sign-in cookie is
// first-party (no cross-site cookie rules) and only one public address is needed.
const API_TARGET = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Lets a second dev server run from the same folder (an isolated test copy) without clashing.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  // Streamed answers must not be buffered for compression on their way through the proxy.
  compress: false,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_TARGET}/:path*` }];
  },
};

export default nextConfig;
