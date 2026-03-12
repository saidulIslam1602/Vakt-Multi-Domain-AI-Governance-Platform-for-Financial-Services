/**
 * Runtime proxy → document-service.
 */
import { type NextRequest } from "next/server";
import { proxyRequest } from "@/app/api/_proxy";

const base = () =>
  (process.env.DOCUMENT_SERVICE_URL || "http://localhost:8002") + "/api/v1";

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params.path, "GET", base());
}
export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params.path, "POST", base());
}
export async function PUT(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params.path, "PUT", base());
}
export async function PATCH(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params.path, "PATCH", base());
}
export async function DELETE(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params.path, "DELETE", base());
}
