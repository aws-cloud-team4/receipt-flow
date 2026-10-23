import type { Receipt } from "../api";

/** The most serious review point of a receipt: "error", "warn" or null. */
export const flagLevel = (r: Receipt) =>
  r.review_points?.some((p) => p.level === "error") ? "error"
    : r.review_points?.some((p) => p.level === "warn") ? "warn" : null;

/** Error/warning counts as chips; the full texts on hover. */
export function ReviewFlags({ receipt, later }: { receipt: Receipt; later?: boolean }) {
  const points = receipt.review_points ?? [];
  const errors = points.filter((p) => p.level === "error").length;
  const warns = points.filter((p) => p.level === "warn").length;
  if (!errors && !warns && !later) return <span className="muted">—</span>;
  return (
    <span title={points.map((p) => p.text).join("\n")} style={{ display: "inline-flex", gap: 6, flexWrap: "wrap" }}>
      {errors > 0 && <span className="chip changes_requested">오류 {errors}</span>}
      {warns > 0 && <span className="chip processing">주의 {warns}</span>}
      {later && <span className="chip draft">건너뜀</span>}
    </span>
  );
}
