/**
 * Shared reverse-proxy utility used by all /api/* route handlers.
 *
 * Slash handling (why this works without 308/307 loops):
 *
 *   Browser → Next.js:
 *     `trailingSlash: false` in next.config.js means Next.js never emits a 308
 *     for incoming /api/* URLs regardless of trailing slash. ✅
 *
 *   Next.js proxy → FastAPI:
 *     We do NOT append a trailing slash to the upstream URL.  FastAPI's default
 *     behaviour (redirect_slashes=True, the default) emits a 307 when a route
 *     like @router.get("/") is called as /foo instead of /foo/.  We use
 *     `redirect: "follow"` so Node resolves that 307 entirely server-side —
 *     the browser never sees it. ✅
 *
 *     Crucially, path-parameter routes like @router.get("/{id}") also work
 *     correctly because we do NOT blindly append a slash, so /documents/abc
 *     reaches /documents/abc/ via the 307 follow and then matches. ✅
 */

import { type NextRequest, NextResponse } from "next/server";

export async function proxyRequest(
  req: NextRequest,
  pathSegments: string[],
  method: string,
  upstreamBase: string,
): Promise<NextResponse> {
  const search = req.nextUrl.search ?? "";

  // Join segments and strip any accidental double-slashes or leading slash.
  const path = pathSegments
    .map((s) => s.replace(/^\/+|\/+$/g, ""))
    .filter(Boolean)
    .join("/");

  // No trailing slash appended here.  FastAPI (redirect_slashes=True default)
  // emits a 307 for slash-missing root routes; redirect:"follow" resolves it
  // server-side so the browser never sees a redirect.
  const url = `${upstreamBase}/${path}${search}`;

  // Forward all request headers except hop-by-hop ones.
  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (!["host", "connection", "transfer-encoding"].includes(k.toLowerCase())) {
      headers.set(k, v);
    }
  });

  const isFormData =
    headers.get("content-type")?.includes("multipart/form-data") ?? false;

  const body =
    method === "GET" || method === "DELETE"
      ? undefined
      : isFormData
      ? await req.blob()
      : await req.arrayBuffer();

  let res: Response;
  try {
    res = await fetch(url, {
      method,
      headers,
      body: body as BodyInit,
      // "follow" → Node.js resolves 307/308 server-side; browser never sees a redirect.
      redirect: "follow",
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error(`[proxy] upstream unreachable → ${url}:`, msg);
    return new NextResponse(
      JSON.stringify({ detail: `Upstream service unavailable: ${msg}` }),
      { status: 503, headers: { "Content-Type": "application/json" } },
    );
  }

  // Strip hop-by-hop headers before forwarding the response.
  const resHeaders = new Headers();
  res.headers.forEach((v, k) => {
    if (!["transfer-encoding", "connection"].includes(k.toLowerCase())) {
      resHeaders.set(k, v);
    }
  });

  return new NextResponse(res.body, {
    status: res.status,
    headers: resHeaders,
  });
}
