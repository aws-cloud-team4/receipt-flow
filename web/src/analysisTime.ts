import type { Receipt } from "./api";

/** Actual worker processing time; legacy records without a start mark use upload time. */
export function analysisSeconds(receipt: Pick<Receipt, "timings">): string | null {
  const start = receipt.timings?.analysis_started ?? receipt.timings?.uploaded;
  const finish = receipt.timings?.analysis_finished;
  if (!start || !finish) return null;
  const elapsed = Date.parse(finish) - Date.parse(start);
  if (!Number.isFinite(elapsed) || elapsed < 0) return null;
  return (elapsed / 1000).toFixed(1);
}
