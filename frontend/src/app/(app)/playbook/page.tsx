import type { Metadata } from "next";
import { getServerSession } from "next-auth/next";

import { PlaybookView } from "@/components/playbook-view";
import { Alert } from "@/components/ui/primitives";
import { authOptions } from "@/lib/auth";

export const metadata: Metadata = { title: "Playbook manager" };

export default async function PlaybookPage() {
  const session = await getServerSession(authOptions);

  // Server-side role gate. The backend independently returns 403 for non-admin
  // writes, so this is a UX affordance rather than the control itself.
  if (session?.user?.role !== "ADMIN") {
    return (
      <Alert variant="warning" title="Admin access required">
        The Playbook Manager is restricted to Admins, because playbook rules directly determine how
        every clause is scored. Sign in as <code className="font-mono">admin@dharma.ai</code> to
        manage rules.
      </Alert>
    );
  }

  return <PlaybookView />;
}
