import type { Metadata } from "next";

import { SearchView } from "@/components/search-view";

export const metadata: Metadata = { title: "Semantic search" };

export default function SearchPage() {
  return <SearchView />;
}
