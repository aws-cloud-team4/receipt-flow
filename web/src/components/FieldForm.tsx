import { useEffect, useRef, useState } from "react";
import type { FieldKey, Fields, Receipt } from "../api";
import { InfoLink } from "./Help";
import { AI_FIELDS, AMOUNT_FIELDS, CATEGORIES, EXPENSE_FIELDS, FIELD_LABELS, PROFILE_FIELDS, REQUIRED } from "../labels";

interface Props {
  receipt: Receipt;
  editable: boolean;
  missing: FieldKey[];
  onSave: (fields: Fields) => Promise<void>;
  /** Bumped by the assistant's "직접 수정": open the form and focus this field. */
  focus?: { field: FieldKey | null; n: number };
}

function toText(key: FieldKey, v: unknown) {
  if (v == null) return "";
  if (AMOUNT_FIELDS.includes(key)) return Number(v).toLocaleString("ko-KR");
  return key === "transaction_at" ? String(v).replace("T", " ") : String(v);
}

const PLACEHOLDER: Partial<Record<FieldKey, string>> = {
  transaction_at: "2026-10-14 12:30",
  business_number: "000-00-00000",
  total_amount: "0",
  card_number: "1234-56**-****-7890",
  approval_number: "30012345",
};

/**
 * Manual editing below the assistant. Saves each field on blur; values being typed are never overwritten.
 * Fields the AI filled carry an "AI" tag until a person changes them.
 */
export default function FieldForm({ receipt, editable, missing, onSave, focus }: Props) {
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [open, setOpen] = useState(true);
  const dirty = useRef(new Set<FieldKey>());
  const box = useRef<HTMLElement>(null);
  const aiFilled = new Set(receipt.ai_filled ?? []);
  // what the reviewer asked to look at again, shown until the receipt is submitted again
  const requested = new Set(receipt.review_status === "changes_requested" ? receipt.review_fields ?? [] : []);
  const requestedFields = (Object.keys(FIELD_LABELS) as FieldKey[]).filter((k) => requested.has(k));

  useEffect(() => {
    if (!focus?.n) return;
    setOpen(true);
    requestAnimationFrame(() => {
      box.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      document.getElementById(`f-${focus.field ?? "merchant_name"}`)?.focus({ preventScroll: true });
    });
  }, [focus?.n]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setDraft((prev) => {
      const next = { ...prev };
      for (const key of [...AI_FIELDS, ...EXPENSE_FIELDS, ...PROFILE_FIELDS]) {
        if (!dirty.current.has(key)) next[key] = toText(key, receipt.fields[key]);
      }
      return next;
    });
  }, [receipt.fields]);

  async function commit(key: FieldKey) {
    if (!dirty.current.has(key)) return;
    let value: string | null = draft[key].trim() || null;
    if (key === "transaction_at" && value) value = value.replace(" ", "T");
    try {
      await onSave({ [key]: value } as Fields);
    } finally {
      dirty.current.delete(key);
    }
  }

  const analyzing = ["waiting", "queued", "processing"].includes(receipt.analysis_status);

  function input(key: FieldKey, full = false) {
    const check = receipt.needs_check.includes(key);
    const isMissing = missing.includes(key);
    return (
      <div key={key} className={`field${check ? " check" : ""}${isMissing ? " missing" : ""}${requested.has(key) ? " requested" : ""}${full ? " full" : ""}`}>
        <label htmlFor={`f-${key}`}>
          <span>
            {FIELD_LABELS[key]} {REQUIRED.includes(key) && <span className="req">*</span>}
          </span>
          <span className="field-tags">
            {requested.has(key) && <span className="request-tag">보완 요청</span>}
            {aiFilled.has(key) && <span className="ai-tag">AI</span>}
            {check && <span className="hint">확인 필요</span>}
          </span>
        </label>
        <input
          id={`f-${key}`}
          value={draft[key] ?? ""}
          disabled={!editable}
          inputMode={AMOUNT_FIELDS.includes(key) ? "numeric" : undefined}
          placeholder={analyzing && AI_FIELDS.includes(key) ? "분석 중…" : PLACEHOLDER[key] ?? ""}
          onChange={(e) => {
            dirty.current.add(key);
            setDraft((d) => ({ ...d, [key]: e.target.value }));
          }}
          onBlur={() => commit(key)}
          onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
        />
      </div>
    );
  }

  // Fixed list: saved as soon as it changes (no free text).
  function categorySelect() {
    const isMissing = missing.includes("category");
    return (
      <div className={`field${isMissing ? " missing" : ""}${requested.has("category") ? " requested" : ""}`}>
        <label htmlFor="f-category">
          <span>
            {FIELD_LABELS.category} <span className="req">*</span><InfoLink topic="categories" />
          </span>
          <span className="field-tags">
            {requested.has("category") && <span className="request-tag">보완 요청</span>}
            {aiFilled.has("category") && <span className="ai-tag">AI 추천</span>}
          </span>
        </label>
        <select
          id="f-category"
          value={receipt.fields.category ?? ""}
          disabled={!editable}
          onChange={(e) => onSave({ category: (e.target.value || null) as Fields["category"] })}
        >
          <option value="">선택하세요</option>
          {Object.entries(CATEGORIES).map(([code, label]) => (
            <option key={code} value={code}>{label}</option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <section className="panel" ref={box}>
      <button type="button" className="panel-head panel-toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <h2>
          <span className={`chevron${open ? " open" : ""}`} aria-hidden>›</span> 증빙 정보
        </h2>
        <span className="muted small">{editable ? "직접 고치기 · 칸을 벗어나면 저장돼요" : "읽기 전용"}</span>
      </button>
      <div className="panel-body form-grid" hidden={!open}>
        {(requestedFields.length > 0 || requested.has("photo")) && (
          <div className="alert error full request-summary">
            <b>보완 요청</b>
            <span>
              {[
                requested.has("photo") ? "사진 다시 찍기" : null,
                requestedFields.length ? `${requestedFields.map((k) => FIELD_LABELS[k]).join(", ")} 칸을 확인해 주세요.` : null,
              ].filter(Boolean).join(" · ")}
            </span>
          </div>
        )}
        <div className="section-title full">영수증에서 읽은 정보<InfoLink topic="amounts" /></div>
        {input("merchant_name", true)}
        {input("transaction_at")}
        {input("total_amount")}
        {input("supply_amount")}
        {input("vat_amount")}
        {input("exempt_amount")}
        {input("payment_method")}
        {input("business_number")}
        {input("card_issuer")}
        {input("card_number")}
        {input("approval_number")}
        <div className="section-title full" style={{ marginTop: 8 }}>지출 정보</div>
        {categorySelect()}
        <div className="field">
          <label htmlFor="f-department">
            <span>{FIELD_LABELS.department}</span>
            <span className="muted small">프로필</span>
          </label>
          <input id="f-department" value={receipt.fields.department ?? ""} disabled readOnly />
        </div>
        {input("purpose", true)}
      </div>
    </section>
  );
}
