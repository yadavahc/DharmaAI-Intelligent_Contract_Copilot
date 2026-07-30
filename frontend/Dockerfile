# Multi-stage build. `output: "standalone"` in next.config.ts produces a minimal
# server bundle, so the runtime image carries only what is needed to serve.
FROM node:22-alpine AS deps
WORKDIR /app
# libc6-compat is required by Next's SWC binary on Alpine.
RUN apk add --no-cache libc6-compat
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:22-alpine AS builder
WORKDIR /app
RUN apk add --no-cache libc6-compat openssl
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* is inlined into the client bundle at build time, so it must be
# the URL the browser can reach — not the compose service name.
ARG NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_TELEMETRY_DISABLED=1

# Prisma's client must be generated before the build imports it. A placeholder
# DATABASE_URL is enough for `generate`; it never connects at build time.
ENV DATABASE_URL="postgresql://placeholder:placeholder@localhost:5432/placeholder"
RUN npx prisma generate
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
RUN apk add --no-cache openssl
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# `public/` is copied via a glob so the build does not hard-fail if the directory
# is empty or absent — a bare `COPY /app/public` errors with "not found", which is
# a confusing way to break an image over static assets.
COPY --from=builder /app/publi[c] ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
# Prisma schema + generated engine are needed at runtime for `prisma db push`
# and for the client itself.
COPY --from=builder --chown=nextjs:nodejs /app/prisma ./prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/@prisma ./node_modules/@prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/prisma ./node_modules/prisma

USER nextjs
EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Push the auth schema on boot so a fresh Postgres volume works with no manual
# migration step, then start the server. `db push` is idempotent.
# `db push` is scoped to the `auth` schema (?schema=auth in DATABASE_URL), so it
# only ever touches Prisma's own tables. Deliberately NO --accept-data-loss: if
# push ever wants to drop something, that is a bug to surface, not to rubber-stamp.
CMD ["sh", "-c", "node node_modules/prisma/build/index.js db push --skip-generate || echo 'prisma db push failed; auth tables may be missing'; node server.js"]
