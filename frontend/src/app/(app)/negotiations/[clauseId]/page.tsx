import type { Metadata } from "next";

import { AgentTheater } from "@/components/agent-theater";

export const metadata: Metadata = { title: "Negotiation workspace" };

export default async function NegotiationPage({
  params,
}: {
  params: Promise<{ clauseId: string }>;
}) {
  const { clauseId } = await params;
  return <AgentTheater clauseId={clauseId} />;
}
