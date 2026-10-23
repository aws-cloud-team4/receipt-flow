import type { FieldKey } from "./api";

/** What the employee is asked to look at again ("photo" = take the photo again). */
export type RequestTarget = FieldKey | "photo";

/** One line of a change request, picked from a review point, a field or a photo preset. */
export interface RequestItem {
  key: string;
  label: string;
  text: string;
  fields: RequestTarget[];
}

export const MAX_REASON = 500; // same limits as the API (ChangeRequest)
export const MAX_FIELDS = 10;

/** 을/를, 이/가 … by whether the word ends in a final consonant (Hangul only). */
export function josa(word: string, withFinal: string, withoutFinal: string): string {
  const code = word.charCodeAt(word.length - 1) - 0xac00;
  if (code < 0 || code > 11171) return withoutFinal;
  return code % 28 ? withFinal : withoutFinal;
}

export const PHOTO_REQUESTS: RequestItem[] = [
  {
    key: "photo:blurry", label: "사진이 흐림", fields: ["photo"],
    text: "사진이 흐려 내용을 확인하기 어려워요. 선명하게 다시 찍어 올려 주세요.",
  },
  {
    key: "photo:cut", label: "영수증 일부가 잘림", fields: ["photo"],
    text: "영수증 일부가 잘려 있어요. 전체가 보이게 다시 찍어 올려 주세요.",
  },
];

const PURPOSE_DETAIL = "어떤 업무를 위해 쓴 비용인지 지출 목적을 구체적으로 적어 주세요.";

/** The request a review point suggests; null when the point is only for the reviewer. */
export function pointRequest(
  point: { code: string; fields?: FieldKey[] },
  labelOf: (key: FieldKey) => string,
): RequestItem | null {
  const fields = point.fields ?? [];
  const names = fields.map(labelOf).join(", ");
  const item = (label: string, text: string, targets: RequestTarget[]): RequestItem =>
    ({ key: `point:${point.code}`, label, text, fields: targets });
  switch (point.code) {
    case "amount_mismatch":
      return item("금액 검산 오류", "공급가액·부가세와 총액이 맞지 않아요. 영수증과 비교해 금액을 수정해 주세요.",
        ["supply_amount", "vat_amount", "total_amount"]);
    case "late_night":
      return item("심야 사유", "심야에 결제한 업무상 사유를 지출 목적에 적어 주세요.", ["purpose"]);
    case "weekend":
      return item("주말 사유", "주말에 결제한 업무상 사유를 지출 목적에 적어 주세요.", ["purpose"]);
    case "duplicate":
    case "same_approval":
      return item("중복 의심", "이미 제출한 증빙과 같은 거래로 보여요. 다른 거래라면 지출 목적에 차이를 적어 주세요.", ["purpose"]);
    case "unclear_fields":
      return fields.length
        ? item("흐리게 읽힌 칸", `흐리게 읽힌 ${names}${josa(names, "을", "를")} 사진과 비교해 확인해 주세요.`, fields)
        : null;
    case "edited_fields":
      return fields.length
        ? item("직접 고친 칸", `직접 입력·수정한 ${names}${josa(names, "을", "를")} 영수증과 다시 비교해 주세요.`, fields)
        : null;
    case "entertainment":
      return item("거래처 누락", "접대 상대 거래처명을 지출 목적에 추가해 주세요.", ["purpose"]);
    case "other_category":
    case "short_purpose":
      return item("목적 구체화", PURPOSE_DETAIL, ["purpose"]);
    default:
      return null;
  }
}

/** The request for one field, quoting what was submitted (`shown`, already formatted). */
export function fieldRequest(key: FieldKey, label: string, shown: string | null): RequestItem {
  const value = shown && shown !== "—" ? `(${shown})` : "";
  const text =
    key === "purpose" ? PURPOSE_DETAIL
    : key === "category" ? `지출 분류${value}가 지출 목적에 맞는지 확인하고 수정해 주세요.`
    : value ? `${label}${value}${josa(label, "을", "를")} 영수증과 비교해 수정해 주세요.`
    : `${label}${josa(label, "을", "를")} 영수증을 보고 입력해 주세요.`;
  return { key: `field:${key}`, label, text, fields: [key] };
}

/** Adds the item, or takes it out when it is already in. */
export function toggleItem(items: RequestItem[], item: RequestItem): RequestItem[] {
  return items.some((i) => i.key === item.key) ? items.filter((i) => i.key !== item.key) : [...items, item];
}

/** The default wording when the reviewer writes nothing: one line per item, same wording once. */
export const defaultReason = (items: RequestItem[]) => [...new Set(items.map((i) => i.text))].join("\n");

/**
 * The `{reason, fields}` body. Items only pick the fields to fix; the reviewer's own reason replaces
 * the default wording, which is sent when the reason is left empty.
 */
export function composeRequest(items: RequestItem[], reason: string): { reason: string; fields: RequestTarget[] } {
  return { reason: reason.trim() || defaultReason(items), fields: [...new Set(items.flatMap((i) => i.fields))] };
}

/** A retake starts the receipt over, so field requests next to it are only hints. */
export const asksRetake = (items: RequestItem[]) => items.some((i) => i.fields.includes("photo"));
