import type { Metadata } from "next";

import { ClauseWorkspace } from "@/components/clause-workspace";

export const metadata: Metadata = { title: "Clause workspace" };

export default async function ClausePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ClauseWorkspace clauseId={id} />;
}
