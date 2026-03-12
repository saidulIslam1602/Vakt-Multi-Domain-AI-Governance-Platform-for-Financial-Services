/**
 * Runtime proxy → ingest-service.
 * Reads INGEST_SERVICE_URL at request time so Docker env vars work correctly
 * with the Next.js standalone build (rewrites in next.config.js are baked at build time).
 */
import { type NextRequest, NextResponse } from "next/server";

const upstream = () =>
  (process.env.INGEST_SERVICE_URL || "http://localhost:8001") + "/api/v1";

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path, "GET");
}
export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path, "POST");
}
export async function PUT(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path, "PUT");
}
export async function PATCH(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path, "PATCH");
}
export async function DELETE(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxy(req, params.path, "DELETE");
}

async function proxy(req: NextRequest, pathSegments: string[], method: string) {
  const search = req.nextUrl.search ?? "";
  const path = pathSegments.join("/");
  const url = `${upstream()}/${path}/${search}`;

  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (!["host", "connection"].includes(k.toLowerCase())) headers.set(k, v);
  });

  const isFormData =
    headers.get("content-type")?.includes("multipart/form-data") ?? false;

  const body =
    method === "GET" || method === "DELETE"
      ? undefined
      : isFormData
      ? await req.blob()
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
