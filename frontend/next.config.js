/** @type {import('next').NextConfig} */
const INGEST_URL  = process.env.INGEST_SERVICE_URL  || "http://ingest-service:8000";
const DOCUMENT_URL = process.env.DOCUMENT_SERVICE_URL || "http://document-service:8000";
const SEARCH_URL  = process.env.SEARCH_SERVICE_URL  || "http://search-service:8000";
const CHAT_URL    = process.env.CHAT_SERVICE_URL    || "http://chat-service:8000";

const nextConfig = {
  output: "standalone",

  async rewrites() {
    return [
      // Ingest service
      {
        source: "/api/ingest/:path*",
        destination: `${INGEST_URL}/api/v1/:path*`,
      },
      // Document service
      {
        source: "/api/documents/:path*",
        destination: `${DOCUMENT_URL}/api/v1/:path*`,
      },
      // Search service
      {
        source: "/api/search/:path*",
        destination: `${SEARCH_URL}/api/v1/:path*`,
      },
      // Chat service
      {
        source: "/api/chat/:path*",
        destination: `${CHAT_URL}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
