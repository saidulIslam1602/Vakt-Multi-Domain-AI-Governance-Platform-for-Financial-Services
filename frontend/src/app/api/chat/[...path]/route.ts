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
  // Always include trailing slash to avoid 307 redirects from FastAPI
  const path = pathSegments.join("/");
  const url = `${upstream()}/${path}/${search}`;

  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (!["host", "connection"].includes(k.toLowerCase())) headers.set(k, v);
  });

  const body =
    method === "GET" || method === "DELETE"
      ? undefined
      : await req.arrayBuffer();

  const res = await fetch(url, { method, headers, body: body as BodyInit, redirect: "follow" });

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
