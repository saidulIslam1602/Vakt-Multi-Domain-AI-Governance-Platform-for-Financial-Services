/**
 * Runtime proxy → search-service.
 */
import { type NextRequest, NextResponse } from "next/server";

const upstream = () =>
  (process.env.SEARCH_SERVICE_URL || "http://localhost:8003") + "/api/v1";

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path, "GET");
}
export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path, "POST");
}

async function proxy(req: NextRequest, pathSegments: string[], method: string) {
  const search = req.nextUrl.search ?? "";
  const path = pathSegments.join("/");
  const url = `${upstream()}/${path}/${search}`;

  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (!["host", "connection"].includes(k.toLowerCase())) headers.set(k, v);
  });

  const body =
    method === "GET"
      ? undefined
      : await req.arrayBuffer();

  const res = await fetch(url, { method, headers, body: body as BodyInit, redirect: "manual" });

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
