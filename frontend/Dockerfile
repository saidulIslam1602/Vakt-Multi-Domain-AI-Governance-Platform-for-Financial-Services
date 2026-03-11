# syntax=docker/dockerfile:1.6
FROM node:20-alpine AS base

WORKDIR /app

FROM base AS deps
COPY package.json package-lock.json* ./
# Install ALL dependencies (including devDeps) so TypeScript is available at build time.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

FROM base AS builder
ENV NODE_ENV=production
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM base AS runtime
RUN addgroup --system allergo && adduser --system --ingroup allergo allergo

COPY --from=builder --chown=allergo:allergo /app/.next/standalone ./
COPY --from=builder --chown=allergo:allergo /app/.next/static ./.next/static
# public/ may be empty; copy only if the directory has content
COPY --from=builder --chown=allergo:allergo /app/public ./public

USER allergo
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

HEALTHCHECK --interval=15s --timeout=5s CMD wget -qO- --server-response http://localhost:3000/ 2>&1 | grep -qE "^  HTTP/[0-9.]+ [23]" || exit 1

CMD ["node", "server.js"]
