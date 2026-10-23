import type { Receipt } from "./api";

/** Compare instants, not ISO strings: stored timestamps can use Z or +09:00. */
export function compareSubmissionTime(a: Pick<Receipt, "submitted_at">, b: Pick<Receipt, "submitted_at">) {
  const instant = (value: string | null) => {
    const parsed = value ? Date.parse(value) : 0;
    return Number.isFinite(parsed) ? parsed : 0;
  };
  return instant(a.submitted_at) - instant(b.submitted_at);
}

/** Keep skipped receipts at the back in skip order. Do not mutate the server result. */
export function orderForReview(queue: Receipt[], later: string[]): Receipt[] {
  const rank = (r: Receipt) => later.indexOf(r.id);
  const oldest = [...queue].sort(compareSubmissionTime);
  return [...oldest.filter((r) => rank(r) < 0), ...oldest.filter((r) => rank(r) >= 0).sort((a, b) => rank(a) - rank(b))];
}
