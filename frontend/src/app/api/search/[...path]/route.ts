/**
 * Runtime proxy → search-service.
 */
import { type NextRequest } from "next/server";
import { proxyRequest } from "@/app/api/_proxy";

const base = () =>
  (process.env.SEARCH_SERVICE_URL || "http://localhost:8003") + "/api/v1";

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params.path, "GET", base());
}
export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  return proxyRequest(req, params.path, "POST", base());
}
