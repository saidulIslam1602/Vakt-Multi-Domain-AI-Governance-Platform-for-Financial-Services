/**
 * Runtime proxy → chat-service.
 */
import { type NextRequest, NextResponse } from "next/server";

const upstream = () =>
  (process.env.CHAT_SERVICE_URL || "http://localhost:8004") + "/api/v1";

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path, "GET");
}
export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path, "POST");
}
export async function DELETE(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path, "DELETE");
}

async function proxy(req: NextRequest, pathSegments: string[], method: string) {
  const search = req.nextUrl.search ?? "";
  const path = pathSegments.join("/");
  // Append trailing slash to the upstream URL so FastAPI routes match without
  // issuing a 307 redirect. The slash must be on the upstream fetch URL, NOT
  // on the Next.js /api/* path (which causes Next.js to emit a 308 itself).
  const url = `${upstream()}/${path}/${search}`;

  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (!["host", "connection"].includes(k.toLowerCase())) headers.set(k, v);
  });

  const body =
    method === "GET" || method === "DELETE"
      ? undefined
      : await req.arrayBuffer();

  let res: Response;
  try {
    // Use redirect:"manual" so a 307/308 from FastAPI is returned as-is rather
    // than Node.js re-issuing the request without the body (which loses POST data).
    res = await fetch(url, { method, headers, body: body as BodyInit, redirect: "manual" });
  } catch (err) {
    const message = err instanceof Error ? err.message : "upstream unreachable";
    console.error(`[chat-proxy] fetch failed → ${url}:`, message);
    return new NextResponse(
      JSON.stringify({ detail: `Chat service unavailable: ${message}` }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }

  const resHeaders = new Headers();
  res.headers.forEach((v, k) => {
    if (!["transfer-encoding", "connection"].includes(k.toLowerCase()))
      resHeaders.set(k, v);
  });

  return new NextResponse(res.body, {
    status: res.status,
    headers: resHeaders,
  });
}
