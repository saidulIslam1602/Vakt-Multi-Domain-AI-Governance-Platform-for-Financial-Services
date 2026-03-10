/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/ingest/:path*",
        destination: `${process.env.INGEST_SERVICE_URL || "http://localhost:8001"}/api/v1/:path*`,
      },
      {
        source: "/api/documents/:path*",
        destination: `${process.env.DOCUMENT_SERVICE_URL || "http://localhost:8002"}/api/v1/:path*`,
      },
      {
        source: "/api/search/:path*",
        destination: `${process.env.SEARCH_SERVICE_URL || "http://localhost:8003"}/api/v1/:path*`,
      },
      {
        source: "/api/chat/:path*",
        destination: `${process.env.CHAT_SERVICE_URL || "http://localhost:8004"}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
