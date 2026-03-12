/**
 * Shared reverse-proxy utility used by all /api/* route handlers.
 *
 * Slash handling (why this works without 308/307 loops):
 *
 *   Browser → Next.js:
 *     `trailingSlash: false` in next.config.js means Next.js never emits a 308
 *     for incoming /api/* URLs regardless of trailing slash. ✅
 *
 *   Next.js proxy → Backend services (internal Container Apps DNS):
 *     Service URLs use internal Container Apps DNS names (http://chat-service,
 *     http://document-service, etc.) — traffic never leaves the environment,
 *     no TLS, no egress, no DNS lookup failures.
 *
 *     We ALWAYS append a trailing slash to the upstream URL. FastAPI routes are
 *     defined as @router.get("/") and @router.get("/{id}") — both accept a
 *     trailing slash directly (200), so we never trigger a 307 redirect.
 *     This is critical for POST/streaming endpoints where following a 307 would
 *     require a second connection and can cause "fetch failed" errors. ✅
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

  // Append trailing slash unless:
  //   (a) the last segment looks like a file (has an extension, e.g. "export.csv"), or
  //   (b) the last segment is a UUID/ID — PATCH/PUT/DELETE on /{id} routes do NOT
  //       have a trailing-slash variant in FastAPI, so appending "/" causes a 404/307.
  const lastSegment = pathSegments[pathSegments.length - 1] ?? "";
  const hasExtension = /\.\w+$/.test(lastSegment);
  const isId =
    // UUID v4 (e.g. "3f2504e0-4f89-11d3-9a0c-0305e82c3301")
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(lastSegment) ||
    // Short alphanumeric IDs without hyphens (e.g. CUID, nanoid ≥ 10 chars)
    /^[a-z0-9]{10,}$/i.test(lastSegment);
  const url = hasExtension || isId
    ? `${upstreamBase}/${path}${search}`
    : `${upstreamBase}/${path}/${search}`;

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
