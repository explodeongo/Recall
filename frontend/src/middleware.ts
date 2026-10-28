import { NextResponse, type NextRequest } from "next/server";

const PUBLIC = ["/login", "/signup", "/demo"];

/** Send signed-out visitors to the log-in page. The API still checks every request; this only
 *  saves a round trip to an empty, failing page. */
export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const signedIn = request.cookies.has("recall_session");
  if (!signedIn && !PUBLIC.includes(pathname)) {
    const url = new URL("/login", request.url);
    if (pathname !== "/") url.searchParams.set("next", pathname + search);
    return NextResponse.redirect(url);
  }
  if (signedIn && PUBLIC.includes(pathname)) return NextResponse.redirect(new URL("/", request.url));
  return NextResponse.next();
}

export const config = {
  // Everything except the API proxy, Next's own files and static assets.
  matcher: ["/((?!api|_next|icons/|icon|apple-icon|manifest.webmanifest|.*\\.(?:png|svg|ico|txt)$).*)"],
};
