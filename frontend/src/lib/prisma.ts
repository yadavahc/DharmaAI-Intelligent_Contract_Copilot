import { PrismaClient } from "@prisma/client";

/**
 * Single Prisma client.
 *
 * Cached on `globalThis` because Next's dev server re-evaluates modules on every
 * hot reload; without this each reload opens a new connection pool until Postgres
 * refuses connections.
 */
const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

export const prisma =
  globalForPrisma.prisma ??
  new PrismaClient({
    log: process.env.NODE_ENV === "development" ? ["error", "warn"] : ["error"],
  });

if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = prisma;
