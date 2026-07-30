import type { Metadata } from "next";

import { ContractsListView } from "@/components/contracts-list-view";

export const metadata: Metadata = { title: "Contracts" };

export default function ContractsPage() {
  return <ContractsListView />;
}
