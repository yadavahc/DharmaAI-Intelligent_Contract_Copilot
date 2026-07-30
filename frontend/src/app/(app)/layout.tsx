import { getServerSession } from "next-auth/next";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { authOptions } from "@/lib/auth";

/**
 * Layout for every authenticated route.
 *
 * The session check here is the gate for the whole `(app)` group — one place
 * rather than per page. Backend authorisation is independent of this: signing in
 * grants access to the UI, not to privileged operations.
 */
export default async function AppLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const session = await getServerSession(authOptions);

  if (!session?.user) {
    redirect("/signin?callbackUrl=/dashboard");
  }

  return <AppShell>{children}</AppShell>;
}
