import type { Metadata } from "next";

import { NegotiationsListView } from "@/components/negotiations-list-view";

export const metadata: Metadata = { title: "Negotiations" };

export default function NegotiationsPage() {
  return <NegotiationsListView />;
}
