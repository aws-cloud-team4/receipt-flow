import type { AnalysisStatus, ReviewStatus } from "../api";
import { ANALYSIS_LABEL, REVIEW_LABEL } from "../labels";

export function ReviewChip({ status }: { status: ReviewStatus }) {
  return <span className={`chip ${status}`}>{REVIEW_LABEL[status]}</span>;
}

export function AnalysisChip({ status }: { status: AnalysisStatus }) {
  return <span className={`chip ${status}`}>{ANALYSIS_LABEL[status]}</span>;
}
