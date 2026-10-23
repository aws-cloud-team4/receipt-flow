import type { Receipt } from "./api";
import { readList, writeList } from "./userStore";

/** A receipt this person opened lately. Kept in this browser only, per user, newest first. */
export interface RecentOpen {
  id: string;
  merchant: string | null;
  at: string;
}

const MAX = 10;

export const recentOpened = () => readList<RecentOpen>("recent");

export function rememberOpen(r: Receipt) {
  const entry = { id: r.id, merchant: r.fields.merchant_name ?? null, at: new Date().toISOString() };
  writeList("recent", [entry, ...recentOpened().filter((e) => e.id !== r.id)].slice(0, MAX));
}

export function forgetOpen(id: string) {
  writeList("recent", recentOpened().filter((e) => e.id !== id));
}
