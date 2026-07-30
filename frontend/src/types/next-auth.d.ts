import type { DefaultSession } from "next-auth";

import type { UserRole } from "@/lib/types";

/** Augment the session/JWT with the role Dharma AI authorises against. */
declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      role: UserRole;
    } & DefaultSession["user"];
  }

  interface User {
    role?: UserRole;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    role?: UserRole;
    uid?: string;
  }
}
