import type { Metadata } from "next";

import { ContractReviewView } from "@/components/contract-review-view";

export const metadata: Metadata = { title: "Contract review" };

export default async function ContractPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ContractReviewView contractId={id} />;
}
