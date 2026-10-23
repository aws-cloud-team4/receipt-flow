import type { Receipt } from "./api";
import { categoryLabel } from "./labels";

const norm = (s: string) => s.toLowerCase().replace(/\s+/g, "");

/** Quick text filter for receipt lists: submitter, employee number, shop, purpose, approval and
 * business numbers, category, date (2026-10-14 or 10-14) and amount (35500 or 35,500). Spaces and
 * case are ignored. */
export function matches(r: Receipt, query: string): boolean {
  const q = norm(query);
  if (!q) return true;
  const f = r.fields;
  const text = norm(
    [r.owner_name, r.owner_profile?.employee_no, f.merchant_name, f.purpose, f.approval_number, f.business_number,
      f.card_issuer, categoryLabel(f.category), f.transaction_at?.replace("T", " ")].filter(Boolean).join("|"),
  );
  if (text.includes(q)) return true;
  const digits = q.replace(/[,원]/g, "");
  return /^\d{3,}$/.test(digits) && f.total_amount != null && String(f.total_amount).includes(digits);
}
