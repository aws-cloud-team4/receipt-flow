import type { AnalysisStatus, CategoryCode, FieldKey, ReviewStatus } from "./api";

export const FIELD_LABELS: Record<FieldKey, string> = {
  merchant_name: "상호명",
  business_number: "사업자번호",
  transaction_at: "거래 일시",
  supply_amount: "공급가액",
  vat_amount: "부가세",
  exempt_amount: "면세금액",
  total_amount: "총액",
  payment_method: "결제수단",
  card_issuer: "카드사",
  card_number: "카드번호",
  approval_number: "승인번호",
  category: "지출 분류",
  purpose: "지출 목적",
  department: "부서",
};

export const AI_FIELDS: FieldKey[] = [
  "merchant_name",
  "transaction_at",
  "total_amount",
  "supply_amount",
  "vat_amount",
  "exempt_amount",
  "payment_method",
  "business_number",
  "card_issuer",
  "card_number",
  "approval_number",
];
export const EXPENSE_FIELDS: FieldKey[] = ["category", "purpose"];
// From the login profile; shown but never edited (receiptflow_common.domain.PROFILE_FIELDS).
export const PROFILE_FIELDS: FieldKey[] = ["department"];

// Same codes as receiptflow_common.domain.CATEGORIES (docs/contract.md).
export const CATEGORIES: Record<CategoryCode, string> = {
  food: "식사·간식비",
  entertainment: "접대·선물비",
  travel: "교통·출장비",
  delivery: "우편·배송비",
  supplies: "사무용품·소모품비",
  education: "도서·교육비",
  welfare_event: "행사·복리후생비",
  subscription: "통신·구독비",
  marketing: "광고·홍보비",
  other: "기타 업무비",
};
export const categoryLabel = (code?: string | null) =>
  code ? (CATEGORIES[code as CategoryCode] ?? code) : "—";
export const AMOUNT_FIELDS: FieldKey[] = ["supply_amount", "vat_amount", "exempt_amount", "total_amount"];
export const REQUIRED: FieldKey[] = ["merchant_name", "transaction_at", "total_amount", "category", "purpose"];

export const REVIEW_LABEL: Record<ReviewStatus, string> = {
  draft: "작성 중",
  submitted: "제출",
  changes_requested: "보완 요청",
  approved: "승인",
};

export const ANALYSIS_LABEL: Record<AnalysisStatus, string> = {
  waiting: "사진 대기",
  queued: "분석 대기",
  processing: "분석 중",
  done: "분석 완료",
  failed: "분석 실패",
};

export const ACTION_LABEL: Record<string, string> = {
  created: "작성 시작",
  reuploaded: "사진 다시 올림",
  edited: "정보 수정",
  ai_edited: "AI 정보 수정",
  submitted: "제출",
  approved: "승인",
  changes_requested: "보완 요청",
};

export const won = (n?: number | null) => (n == null ? "—" : `${n.toLocaleString("ko-KR")}원`);

export function shortDate(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export const txDate = (value?: string | null) => (value ? value.replace("T", " ") : "—");
