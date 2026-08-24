import { create } from "zustand";

import type { Citation } from "@/lib/api/client";

interface CitationState {
  selected: Citation | null;
  select: (citation: Citation) => void;
  clear: () => void;
}

export const useCitationStore = create<CitationState>((set) => ({
  selected: null,
  select: (selected) => set({ selected }),
  clear: () => set({ selected: null }),
}));
