import { analysisSeconds } from "../analysisTime";
import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type ChatMessage, type FieldKey, type Me, type Receipt } from "../api";
import { InfoLink } from "../components/Help";
import { clearLater, markLater, reviewOrder } from "../later";
import { forgetOpen, rememberOpen } from "../recent";
import { History, PhotoPanel } from "../components/ReceiptParts";
import { SubNav } from "../components/Shell";
import { ReviewChip } from "../components/StatusChip";
import { AMOUNT_FIELDS, categoryLabel, FIELD_LABELS, PROFILE_FIELDS, txDate, won } from "../labels";
import {
  asksRetake, composeRequest, defaultReason, fieldRequest, MAX_FIELDS, MAX_REASON, PHOTO_REQUESTS, pointRequest, toggleItem,
  type RequestItem,
} from "../reviewReasons";

const ORDER: FieldKey[] = [
  "merchant_name", "transaction_at", "total_amount", "supply_amount", "vat_amount", "exempt_amount",
  "payment_method",
  "business_number", "card_issuer", "card_number", "approval_number", "category", "purpose", "department",
];

export default function ReviewDetail({ me }: { me: Me }) {
  const { id = "" } = useParams();
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  // items (review points, fields, photo presets) pick what to fix; the note is the reason, if written
  const [items, setItems] = useState<RequestItem[]>([]);
  const [note, setNote] = useState("");
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [chat, setChat] = useState<ChatMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();
  // where the reviewer came from (home or the list with its filters); kept while moving to the next one
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/review";
  const backLabel = from === "/" ? "홈으로" : "목록으로";

  useEffect(() => {
    // a new id (the next one in the queue) starts clean
    setReceipt(null);
    setItems([]);
    setNote("");
    setAsking(false);
    setBusy(false);
    setError(null);
    api.get(id).then(
      (r) => {
        setReceipt(r);
        rememberOpen(r);
      },
      (e) => {
        if (e instanceof ApiError && e.status === 404) forgetOpen(id);
        setError(e.message);
      },
    );
    api.chatMessages(id).then(({ items }) => setChat(items), () => setChat([]));
  }, [id]);

  if (error && !receipt) return <main className="page"><div className="alert error">{error}</div></main>;
  if (!receipt) return <div className="empty">불러오는 중…</div>;

  const request = composeRequest(items, note);
  const requestProblem =
    !request.reason ? "요청 항목을 담거나 상세 사유를 적어 주세요."
    : request.reason.length > MAX_REASON ? `요청 문구는 ${MAX_REASON}자까지 보낼 수 있어요.`
    : request.fields.length > MAX_FIELDS ? `다시 볼 칸은 ${MAX_FIELDS}개까지 지정할 수 있어요.`
    : null;

  async function decide(kind: "approve" | "changes") {
    if (kind === "changes" && requestProblem) return;
    setBusy(true);
    setError(null);
    try {
      if (kind === "approve") await api.approve(id);
      else await api.requestChanges(id, request.reason, request.fields);
      clearLater(id);
      await goNext();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  // Straight on to the next one (oldest first, put-off ones last); home when nothing is left.
  async function goNext() {
    const { items } = await api.reviewList("submitted");
    const next = reviewOrder(items.filter((r) => r.id !== id))[0];
    navigate(next ? `/review/${next.id}` : from, { state: { from } });
  }

  async function later() {
    setBusy(true);
    markLater(id);
    try {
      await goNext();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  const value = (k: FieldKey) => {
    const v = receipt.fields[k];
    if (AMOUNT_FIELDS.includes(k)) return won(v as number | null);
    if (k === "transaction_at") return txDate(v as string | null);
    if (k === "category") return categoryLabel(v as string | null);
    return v ?? "—";
  };
  const took = analysisSeconds(receipt);
  const points = receipt.review_points ?? [];

  const reviewing = receipt.review_status === "submitted";
  const picked = (key: string) => items.some((i) => i.key === key);
  function pick(item: RequestItem) {
    setItems((now) => toggleItem(now, item));
    setAsking(true);
  }

  return (
    <>
      <SubNav items={[{ label: "홈", to: "/" }, { label: "검수 목록", to: "/review" }, { label: receipt.fields.merchant_name ?? receipt.id.slice(0, 8) }]} />
      <main className="page">
        <div className="page-head">
          <div>
            <button type="button" className="link-btn back-link" onClick={() => navigate(from)}>← {backLabel}</button>
            <h1>{receipt.fields.merchant_name}</h1>
            <p style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
              <ReviewChip status={receipt.review_status} />
              <span className="muted small">
                제출자 {receipt.owner_name}
                {receipt.owner_profile &&
                  ` · ${[receipt.owner_profile.position, receipt.owner_profile.department, receipt.owner_profile.employee_no]
                    .filter(Boolean)
                    .join(" · ")}`}
              </span>
              {took && <span className="muted small">AI 분석 {took}초</span>}
            </p>
          </div>
        </div>
        <div className="workspace">
          <div className="col photo-col">
            <PhotoPanel receipt={receipt} imageUrl={receipt.image_url ?? null} originalUrl={receipt.original_url ?? null} />
          </div>
          <div className="col">
            <section className="panel">
              <div className="panel-head"><h2>검토 포인트<InfoLink topic="review_points" /></h2></div>
              <div className="panel-body stack">
                {points.length === 0 ? (
                  <div className="muted small">특별히 볼 점이 없어요. 값과 사진만 확인해 주세요.</div>
                ) : (
                  points.map((p, i) => {
                    const suggested = reviewing ? pointRequest(p, (k) => FIELD_LABELS[k]) : null;
                    const on = suggested ? picked(suggested.key) : false;
                    return (
                      <div key={i} className={`alert point ${p.level === "error" ? "error" : p.level === "warn" ? "warn" : "info"}`}>
                        <b>{p.level === "error" ? "오류" : p.level === "warn" ? "주의" : "참고"}</b>
                        <span className="point-text">{p.text}</span>
                        {suggested && (
                          <button type="button" className={`pick-btn${on ? " on" : ""}`} aria-pressed={on} disabled={busy}
                            title={suggested.text} aria-label={`${suggested.label} ${on ? "요청에서 빼기" : "요청에 담기"}`}
                            onClick={() => pick(suggested)}>
                            {on ? "담김 ✓" : "요청에 담기"}
                          </button>
                        )}
                      </div>
                    );
                  })
                )}
                {receipt.review_note && receipt.review_status !== "approved" && (
                  <div className="muted small">지난 보완 요청: “{receipt.review_note}”</div>
                )}
              </div>
            </section>
            <section className="panel">
              <div className="panel-head"><h2>증빙 정보</h2></div>
              <dl className="panel-body kv">
                {ORDER.map((k) => {
                  const flaggable = reviewing && asking && !PROFILE_FIELDS.includes(k);
                  const on = picked(`field:${k}`);
                  return (
                    <div key={k} style={{ display: "contents" }}>
                      <dt>{FIELD_LABELS[k]}</dt>
                      <dd className={flaggable ? "flaggable" : undefined}>
                        <span>{value(k)}</span>
                        {flaggable && (
                          <button type="button" className={`pick-btn${on ? " on" : ""}`} aria-pressed={on} disabled={busy}
                            aria-label={`${FIELD_LABELS[k]} ${on ? "요청에서 빼기" : "수정 요청"}`}
                            onClick={() => pick(fieldRequest(k, FIELD_LABELS[k], String(value(k))))}>
                            {on ? "담김 ✓" : "수정 요청"}
                          </button>
                        )}
                      </dd>
                    </div>
                  );
                })}
              </dl>
            </section>
            {reviewing && asking && (
              <section className="panel panel-body stack change-request" aria-label="보완 요청 작성">
                <h2>보완 요청 작성</h2>
                <p className="muted small">
                  검토 포인트의 [요청에 담기]나 증빙 정보 칸 옆 [수정 요청]을 누르면 요청 항목이 담겨요.
                </p>
                <div className="section-title">
                  담은 요청 {items.length > 0 && <span className="muted small">{items.length}개</span>}
                </div>
                {items.length === 0 ? (
                  <div className="request-empty muted small">아직 담은 항목이 없어요.</div>
                ) : (
                  <div className="request-chips" aria-label="담은 요청">
                    {items.map((item) => (
                      <button key={item.key} type="button" className="pick-btn on" disabled={busy} title={item.text}
                        aria-label={`${item.label} 빼기`} onClick={() => setItems((now) => toggleItem(now, item))}>
                        {item.label} ×
                      </button>
                    ))}
                  </div>
                )}
                <div className="section-title">사진 다시 찍기</div>
                <div className="request-chips">
                  {PHOTO_REQUESTS.map((item) => (
                    <button key={item.key} type="button" className={`pick-btn${picked(item.key) ? " on" : ""}`}
                      aria-pressed={picked(item.key)} disabled={busy} onClick={() => pick(item)}>
                      {picked(item.key) ? `${item.label} ✓` : item.label}
                    </button>
                  ))}
                </div>
                {asksRetake(items) && items.some((i) => !i.fields.includes("photo")) && (
                  <div className="alert warn" role="status">
                    사진을 다시 찍으면 모든 칸·지출 목적·분류가 비워지고 처음부터 다시 작성해요. 다른 항목은 참고 안내로 전달돼요.
                  </div>
                )}
                <label className="section-title" htmlFor="request-note">상세 사유 <span className="muted small">선택</span></label>
                <textarea id="request-note" className="reason" value={note} disabled={busy}
                  aria-describedby="request-note-help"
                  placeholder={items.length ? defaultReason(items) : "직원이 무엇을 보완해야 하는지 적어 주세요."}
                  onChange={(e) => setNote(e.target.value)} />
                <p id="request-note-help" className="muted small">
                  비워 두면 담은 요청의 기본 문구로 보내요. 적으면 적은 내용만 보내요.
                </p>
                {request.reason && (
                  <div className="request-preview" aria-label="직원에게 보이는 메시지">
                    <div className="section-title">직원에게 이렇게 보여요</div>
                    <div className="bubble assistant">{me.name}님이 보완을 요청했어요: “{request.reason}”</div>
                  </div>
                )}
                <p className={request.reason.length > MAX_REASON ? "reason-count error-text" : "reason-count muted"}
                  role={request.reason.length > MAX_REASON ? "alert" : undefined}>
                  {request.reason.length} / {MAX_REASON}자
                </p>
              </section>
            )}
            {chat.length > 0 && (
              <details className="panel chat-transcript">
                <summary className="panel-head"><h2>직원과 AI의 대화 ({chat.length})</h2></summary>
                <div className="panel-body chat-log readonly">
                  {chat.map((m, i) => <div key={i} className={`bubble ${m.role}`}>{m.text}</div>)}
                </div>
              </details>
            )}
            {receipt.history && <History events={receipt.history} />}
          </div>
        </div>
        {reviewing && (
          <div className="sticky-actions">
            {error && <div className="alert error" style={{ flex: "1 1 100%" }}>{error}</div>}
            <span className="spacer" />
            {asking ? (
              <>
                <button className="btn btn-ghost btn-lg" disabled={busy} onClick={() => setAsking(false)}>취소</button>
                <button className="btn btn-danger btn-lg" disabled={busy || !!requestProblem} title={requestProblem ?? undefined}
                  onClick={() => decide("changes")}>
                  보완 요청 보내기
                </button>
              </>
            ) : (
              <>
                <button className="btn btn-ghost btn-lg" disabled={busy} onClick={later}
                  title="판단을 미루고 다음 건으로 — 검토 순서의 맨 뒤로 가요">건너뛰기</button>
                <button className="btn btn-danger btn-lg" onClick={() => setAsking(true)}>보완 요청</button>
                <button className="btn btn-primary btn-lg" disabled={busy} onClick={() => decide("approve")}>승인</button>
              </>
            )}
          </div>
        )}
      </main>
    </>
  );
}
