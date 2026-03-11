/** @type {import('next').NextConfig} */

const nextConfig = {
  output: "standalone",

  // All backend proxying is handled by Route Handlers in src/app/api/*/[...path]/route.ts
  // which read the *_SERVICE_URL env vars at request time. Do NOT add rewrites here —
  // next.config.js rewrites are baked at build time and, when the destination is an
  // external HTTPS URL, Next.js emits a redirect instead of a true server-side proxy,
  // causing redirect loops in the browser.
};

module.exports = nextConfig;
