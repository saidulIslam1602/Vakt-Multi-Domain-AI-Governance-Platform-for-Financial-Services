/**
 * Shared reverse-proxy utility used by all /api/* route handlers.
 *
 * Slash handling:
 *   All backend services use FastAPI with redirect_slashes=False.  Routes
 *   registered as @router.get("/") (e.g. /stats/, /documents/) return a hard
 *   404 — NOT a 307 redirect — when called without the trailing slash.  So the
 *   proxy always appends a trailing slash to the upstream URL.
 *
 *   On the Next.js side, `trailingSlash: false` is set in next.config.js, which
 *   means Next.js never emits a 308 for incoming /api/* requests regardless of
 *   whether they include a trailing slash.  The browser therefore never sees any
 *   redirect at all.
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

  // Always send a trailing slash to the upstream service.
  // All services set redirect_slashes=False in FastAPI, so routes registered
  // as @router.get("/") return a hard 404 (not 307) when called without the
  // trailing slash. We append it here (server-side only).
  // Next.js trailingSlash:false in next.config.js prevents 308 on the
  // *incoming* /api/* URL, so the browser never sees a redirect.
  const url = `${upstreamBase}/${path}/${search}`;

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
