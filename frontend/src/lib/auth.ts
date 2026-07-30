/**
 * NextAuth configuration — Admin / Reviewer / Business User.
 *
 * Credentials provider with bcrypt hashes, backed by Prisma. Three demo accounts
 * are seeded lazily on first sign-in (see `ensureDemoUsers`) so a fresh clone can
 * be logged into without a manual seed step.
 *
 * The role lives on the JWT and is re-read from the database on each token
 * refresh, so an admin changing someone's role takes effect without that user
 * having to sign out. Authorisation is still enforced backend-side; the role in
 * the session only drives what the UI offers.
 */

import { PrismaAdapter } from "@auth/prisma-adapter";
import bcrypt from "bcryptjs";
import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

import { prisma } from "@/lib/prisma";
import type { UserRole } from "@/lib/types";

const DEMO_USERS: { email: string; password: string; name: string; role: UserRole }[] = [
  {
    email: process.env.DEMO_ADMIN_EMAIL || "admin@dharma.ai",
    password: process.env.DEMO_ADMIN_PASSWORD || "admin123",
    name: "Avery Chen",
    role: "ADMIN",
  },
  {
    email: process.env.DEMO_REVIEWER_EMAIL || "reviewer@dharma.ai",
    password: process.env.DEMO_REVIEWER_PASSWORD || "reviewer123",
    name: "Priya Raman",
    role: "REVIEWER",
  },
  {
    email: process.env.DEMO_USER_EMAIL || "user@dharma.ai",
    password: process.env.DEMO_USER_PASSWORD || "user123",
    name: "Jordan Blake",
    role: "BUSINESS_USER",
  },
];

let demoUsersReady: Promise<void> | null = null;

/** Idempotently create the demo accounts. Memoised so it runs once per process. */
export function ensureDemoUsers(): Promise<void> {
  if (!demoUsersReady) {
    demoUsersReady = (async () => {
      for (const user of DEMO_USERS) {
        const passwordHash = await bcrypt.hash(user.password, 10);
        await prisma.user.upsert({
          where: { email: user.email },
          // Keep the seeded password and role authoritative so a demo account
          // cannot drift into an unusable state between runs.
          update: { passwordHash, role: user.role, name: user.name },
          create: {
            email: user.email,
            name: user.name,
            role: user.role,
            passwordHash,
          },
        });
      }
    })().catch((error) => {
      // Reset so a later request can retry (e.g. Postgres still starting up).
      demoUsersReady = null;
      throw error;
    });
  }
  return demoUsersReady;
}

export const authOptions: NextAuthOptions = {
  adapter: PrismaAdapter(prisma) as NextAuthOptions["adapter"],
  session: {
    strategy: "jwt",
    maxAge: 60 * 60 * 8,
  },
  pages: {
    signIn: "/signin",
    error: "/signin",
  },
  providers: [
    CredentialsProvider({
      name: "Email and password",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        const email = credentials?.email?.trim().toLowerCase();
        const password = credentials?.password;
        if (!email || !password) return null;

        try {
          await ensureDemoUsers();
        } catch (error) {
          console.error("[auth] demo user seeding failed:", error);
        }

        const user = await prisma.user.findUnique({ where: { email } });
        if (!user?.passwordHash) return null;

        const valid = await bcrypt.compare(password, user.passwordHash);
        if (!valid) return null;

        return {
          id: user.id,
          email: user.email,
          name: user.name,
          role: user.role,
        };
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.role = (user as { role?: UserRole }).role ?? "BUSINESS_USER";
        token.uid = user.id;
        return token;
      }
      // Re-read the role so a role change applies without a full sign-out.
      if (token.email) {
        try {
          const fresh = await prisma.user.findUnique({
            where: { email: token.email },
            select: { id: true, role: true },
          });
          if (fresh) {
            token.role = fresh.role;
            token.uid = fresh.id;
          }
        } catch {
          // Keep the existing token if the database is briefly unreachable.
        }
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.role = (token.role as UserRole) ?? "BUSINESS_USER";
        session.user.id = (token.uid as string) ?? "";
      }
      return session;
    },
  },
  secret: process.env.NEXTAUTH_SECRET,
};

export const DEMO_CREDENTIALS = DEMO_USERS.map(({ email, password, name, role }) => ({
  email,
  password,
  name,
  role,
}));
