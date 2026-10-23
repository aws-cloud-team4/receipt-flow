import { analysisSeconds } from "../analysisTime";
import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type FieldKey, type Fields, type Receipt } from "../api";
import { forgetOpen, rememberOpen } from "../recent";
import ChatPanel from "../components/ChatPanel";
import FieldForm from "../components/FieldForm";
import { Checks, History, PhotoPanel, SubmitReview } from "../components/ReceiptParts";
import { SubNav } from "../components/Shell";
import { AnalysisChip, ReviewChip } from "../components/StatusChip";

const ANALYZING = ["waiting", "queued", "processing"];

export default function ReceiptWorkspace() {
  const { id = "" } = useParams();
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [originalUrl, setOriginalUrl] = useState<string | null>(null);
  const [missing, setMissing] = useState<FieldKey[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [focus, setFocus] = useState<{ field: FieldKey | null; n: number }>({ field: null, n: 0 });
  const [reviewing, setReviewing] = useState(false); // the final review dialog before submitting
  const navigate = useNavigate();
  // back to 내 증빙 as it was left (tab, filters); kept while skipping to the next one
  const state = useLocation().state as { from?: string } | null;
  const from = state?.from?.startsWith("/receipts") ? state.from : "/receipts";

  const load = useCallback(async () => {
    const r = await api.get(id);
    setReceipt(r);
    // Presigned URLs change on every read; keep the first one so the photo does not flicker.
    setImageUrl((cur) => (r.analysis_status === "waiting" ? null : cur ?? r.image_url ?? null));
    setOriginalUrl((cur) => cur ?? r.original_url ?? null);
    return r;
  }, [id]);

  useEffect(() => {
    load().then(rememberOpen, (e) => {
      if (e instanceof ApiError && e.status === 404) forgetOpen(id);
      setError(e.message);
    });
  }, [load, id]);

  // Poll while extraction runs.
  useEffect(() => {
    if (!receipt || !ANALYZING.includes(receipt.analysis_status) || receipt.analysis_status === "waiting") return;
    const t = setInterval(() => load().catch(() => {}), 1500);
    return () => clearInterval(t);
  }, [receipt?.analysis_status, load]); // eslint-disable-line react-hooks/exhaustive-deps

  if (error && !receipt) return <main className="page"><div className="alert error">{error}</div></main>;
  if (!receipt) return <div className="empty">불러오는 중…</div>;

  const editable = receipt.review_status === "draft" || receipt.review_status === "changes_requested";
  const analyzing = ANALYZING.includes(receipt.analysis_status);
  const took = analysisSeconds(receipt);

  async function save(fields: Fields) {
    try {
      setReceipt(await api.patch(id, fields));
      setMissing((m) => m.filter((k) => !(k in fields)));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function submit() {
    setReviewing(false);
    setBusy("submit");
    setError(null);
    try {
      await api.submit(id);
      setNotice("제출했어요. 담당자 검토 후 결과를 알려 드려요.");
      await load();
    } catch (e) {
      if (e instanceof ApiError && e.fields) setMissing(e.fields);
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  // On to the next thing to do (sent back first, then drafts), going round; 내 증빙 when nothing else is left.
  async function skip() {
    setBusy("skip");
    try {
      const { items } = await api.mine();
      const todo = [
        ...items.filter((r) => r.review_status === "changes_requested"),
        ...items.filter((r) => r.review_status === "draft"),
      ];
      const at = todo.findIndex((r) => r.id === id);
      const next = [...todo.slice(at + 1), ...todo.slice(0, Math.max(at, 0))].find((r) => r.id !== id);
      navigate(next ? `/receipts/${next.id}` : from, { state: { from } });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  // A new photo may be another receipt: the server starts the receipt and the chat over.
  function retake() {
    const entered = receipt?.fields.purpose || receipt?.fields.category || receipt?.result_confirmed_at;
    if (entered && !window.confirm("사진을 다시 올리면 지출 목적·분류와 AI 대화가 지워지고 처음부터 다시 시작해요. 계속할까요?")) {
      return;
    }
    navigate(`/receipts/${id}/photo`);
  }

  async function remove() {
    if (!window.confirm("이 증빙을 삭제할까요? 사진과 대화도 함께 지워지고 되돌릴 수 없어요.")) return;
    setBusy("delete");
    setError(null);
    try {
      await api.remove(id);
      forgetOpen(id);
      navigate(from, { replace: true });
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  return (
    <>
      <SubNav items={[{ label: "내 증빙", to: "/receipts" }, { label: receipt.fields.merchant_name ?? "새 증빙" }]} />
      <main className="page">
        <div className="page-head">
          <div>
            <button type="button" className="link-btn back-link" onClick={() => navigate(from)}>← 내 증빙으로</button>
            <h1>{receipt.fields.merchant_name ?? (analyzing ? "영수증 분석 중" : "증빙 확인")}</h1>
            <p style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
              <ReviewChip status={receipt.review_status} />
              <AnalysisChip status={receipt.analysis_status} />
              {took && <span className="muted small">분석 {took}초</span>}
            </p>
          </div>
        </div>

        {receipt.review_status === "changes_requested" && (
          <div className="alert error" style={{ marginBottom: 14 }}>
            <b>보완 요청</b> {receipt.review_note} — 수정 후 다시 제출해 주세요.
          </div>
        )}
        {receipt.review_status === "approved" && <div className="alert ok" style={{ marginBottom: 14 }}>승인된 증빙입니다.</div>}
        {notice && <div className="alert ok" style={{ marginBottom: 14 }}>{notice}</div>}

        <div className="workspace">
          {/* The photo stays in view while the right column scrolls: values are checked against it. */}
          <div className="col photo-col">
            <PhotoPanel receipt={receipt} imageUrl={imageUrl} originalUrl={originalUrl}
              onRetake={editable && !busy && !analyzing ? retake : undefined} />
          </div>
          <div className="col">
            <ChatPanel receipt={receipt} editable={editable}
              onFieldsChanged={() => load().catch(() => {})}
              onEditRequest={(field) => setFocus((f) => ({ field, n: f.n + 1 }))}
              onSubmit={submit} onRetake={retake} />
            <Checks receipt={receipt} />
            <FieldForm receipt={receipt} editable={editable} missing={missing} onSave={save} focus={focus} />
            {receipt.history && receipt.history.length > 0 && <History events={receipt.history} />}
          </div>
        </div>

        {editable && (
          <div className="sticky-actions">
            {error && <div className="alert error" style={{ flex: "1 1 100%" }}>{error}</div>}
            {/* Destructive action at the far end from submit. */}
            {receipt.review_status === "draft" && (
              <button className="btn btn-text-danger" disabled={!!busy} onClick={remove}>
                {busy === "delete" ? "삭제 중…" : "삭제"}
              </button>
            )}
            <span className="spacer" />
            <button className="btn btn-ghost btn-lg" disabled={!!busy} onClick={skip}
              title="지금은 두고 다음 할 일로 — 보완 요청, 작성 중 순서">{busy === "skip" ? "넘어가는 중…" : "건너뛰기"}</button>
            <button className="btn btn-primary btn-lg" disabled={!!busy || analyzing} onClick={() => setReviewing(true)}>
              {analyzing ? "분석이 끝나면 제출할 수 있어요" : busy === "submit" ? "제출 중…" : "제출하기"}
            </button>
          </div>
        )}
        {reviewing && (
          <div className="dialog-backdrop" role="presentation" onClick={() => setReviewing(false)}>
            <div className="dialog" role="dialog" aria-modal="true" aria-label="제출 전 확인"
              onClick={(e) => e.stopPropagation()}>
              <SubmitReview receipt={receipt} busy={!!busy} onSubmit={submit}
                onEdit={() => { setReviewing(false); setFocus((f) => ({ field: null, n: f.n + 1 })); }} />
            </div>
          </div>
        )}
      </main>
    </>
  );
}
