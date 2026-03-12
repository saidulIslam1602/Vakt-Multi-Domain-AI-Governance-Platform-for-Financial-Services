/**
 * Shared reverse-proxy utility used by all /api/* route handlers.
 *
 * Root cause of the 308 redirect loop:
 *   The old proxy built upstream URLs as `${base}/${path}/` (hard trailing
 *   slash).  When the upstream FastAPI service responded with a 307/308 (e.g.
 *   /stats → /stats/) the old code passed `redirect: "manual"` straight back
 *   to the browser, which then followed the redirect — but without the
 *   Authorization header, producing 401/404 errors.  Separately, Next.js
 *   itself emits a 308 for any incoming request whose pathname ends with a
 *   slash (trailingSlash: false is the default; the slash is stripped).
 *
 * Fix:
 *   1. Build the upstream URL WITHOUT a trailing slash.
 *   2. Use `redirect: "follow"` so Node resolves any 307/308 from FastAPI
 *      entirely on the server side — the browser never sees a redirect.
 *   3. Never forward 3xx status codes to the client.
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

  // NO trailing slash — FastAPI's redirect (307) is resolved by Node below.
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
