import { useState } from "react";
import type { Check, FieldKey, HistoryEvent, Receipt } from "../api";
import { InfoLink } from "./Help";
import { ACTION_LABEL, categoryLabel, FIELD_LABELS, shortDate, txDate, won } from "../labels";

interface PhotoProps {
  receipt: Receipt;
  imageUrl: string | null; // cropped, what the AI read
  originalUrl?: string | null; // the photo as taken
  /** Take or upload the photo again (shown on the photo's toolbar). */
  onRetake?: () => void;
}

/** Cropped receipt by default; reviewers can switch to the original photo to compare. */
export function PhotoPanel({ receipt, imageUrl, originalUrl, onRetake }: PhotoProps) {
  const [showOriginal, setShowOriginal] = useState(false);
  const [expanded, setExpanded] = useState(false); // small screens show a short preview until tapped
  const status = receipt.analysis_status;
  const src = showOriginal && originalUrl ? originalUrl : imageUrl;
  return (
    <div className={`photo${expanded ? " expanded" : ""}`}>
      {onRetake && (
        <button className="photo-retake" onClick={onRetake}>다시 찍기</button>
      )}
      {originalUrl && imageUrl && (
        <div className="photo-toggle segmented" role="group" aria-label="사진 보기">
          <button aria-pressed={!showOriginal} onClick={() => setShowOriginal(false)}>보정본</button>
          <button aria-pressed={showOriginal} onClick={() => setShowOriginal(true)}>원본</button>
        </div>
      )}
      {src ? (
        <img src={src} alt={showOriginal ? "영수증 원본 사진" : "영수증 사진 (보정본)"}
          onClick={() => setExpanded((v) => !v)} />
      ) : (
        <div className="placeholder">사진이 아직 없어요.</div>
      )}
      {(status === "queued" || status === "processing") && (
        <div className="overlay">
          <div>
            <div className="spinner" />
            AI가 영수증을 읽고 있어요
            <div className="small" style={{ opacity: 0.8, fontWeight: 400 }}>그동안 AI 어시스턴트의 질문에 답해 주세요</div>
          </div>
        </div>
      )}
    </div>
  );
}

const REVIEW_FIELDS: FieldKey[] = [
  "merchant_name",
  "transaction_at",
  "total_amount",
  "payment_method",
  "category",
  "purpose",
  "department",
];

/** What will be submitted, with the warnings, right before the submit button (chat card and dialog). */
export function SubmitReview({ receipt, busy, onSubmit, onEdit, submitted = false }: {
  receipt: Receipt;
  busy: boolean;
  onSubmit: () => void;
  onEdit: () => void;
  /** After submitting: a record of what went in, without buttons. */
  submitted?: boolean;
}) {
  const f = receipt.fields;
  const checks = receipt.checks ?? [];
  const errors = checks.filter((c) => c.level === "error");
  const warnings = checks.filter((c) => c.level !== "error");
  const missing = REVIEW_FIELDS.filter((k) => k !== "department" && (f[k] == null || f[k] === ""));
  const value = (k: FieldKey) =>
    k === "total_amount" ? won(f.total_amount)
      : k === "transaction_at" ? txDate(f.transaction_at)
      : k === "category" ? categoryLabel(f.category)
      : k === "payment_method" ? [f.payment_method, f.card_issuer].filter(Boolean).join(" · ") || "—"
      : (f[k] as string) || "—";
  const blocked = errors.length > 0 || missing.length > 0;
  return (
    <div className="result-card final-review">
      <p>{submitted ? "제출한 내용이에요." : "제출할 내용이에요."}</p>
      <dl>
        {REVIEW_FIELDS.map((k) => (
          <div key={k} style={{ display: "contents" }}>
            <dt>{FIELD_LABELS[k]}</dt>
            <dd>{value(k)}</dd>
          </div>
        ))}
      </dl>
      {warnings.map((c) => <div key={c.code} className="review-note warn">⚠ {c.message}</div>)}
      {errors.map((c) => <div key={c.code} className="review-note err">{c.message}</div>)}
      {missing.length > 0 && (
        <div className="review-note err">{missing.map((k) => FIELD_LABELS[k]).join(", ")}을(를) 채워 주세요.</div>
      )}
      {!submitted && <div className="result-actions">
        <button className="btn btn-ghost" disabled={busy} onClick={onEdit}>직접 수정</button>
        <button className="btn btn-primary" disabled={busy || blocked} onClick={onSubmit}>
          {busy ? "제출 중…" : "제출하기"}
        </button>
      </div>}
    </div>
  );
}

export function Checks({ receipt }: { receipt: Receipt }) {
  const checks: Check[] = receipt.checks ?? [];
  if (receipt.analysis_status === "failed") {
    return <div className="alert error">{receipt.analysis_error ?? "분석에 실패했어요."} 직접 입력하거나 다시 올려 주세요.</div>;
  }
  if (!checks.length) return null;
  return (
    <div className="stack">
      {checks.map((c) => (
        <div key={c.code} className={`alert ${c.level === "error" ? "error" : "warn"}`}>
          <b>{c.level === "error" ? "오류" : "확인"}</b> {c.message}<InfoLink topic="checks" />
        </div>
      ))}
    </div>
  );
}

export function History({ events }: { events: HistoryEvent[] }) {
  return (
    <section className="panel">
      <div className="panel-head"><h2>처리 이력</h2></div>
      <div className="panel-body">
        <ol className="timeline">
          {events.map((e) => (
            <li key={e.at + e.action}>
              <time dateTime={e.at}>{shortDate(e.at)}</time>
              <div>
                <b>{ACTION_LABEL[e.action] ?? e.action}</b> <span className="muted">· {e.actor}</span>
                {e.note && <div className="muted">사유: {e.note}</div>}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
