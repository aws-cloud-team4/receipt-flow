import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { admin, type Deletion, type Receipt, type ReviewStatus } from "../api";
import { ReviewChip } from "../components/StatusChip";
import { REVIEW_LABEL, shortDate, txDate, won } from "../labels";

const TABS: ReviewStatus[] = ["draft", "submitted", "changes_requested", "approved"];
type Tab = ReviewStatus | "deleted";

/** Every receipt by status (drafts included); an admin can delete any of them for good. */
export default function AdminReceipts() {
  // the tab lives in the address, so the side menu can link straight to it
  const [params, setParams] = useSearchParams();
  const status = params.get("status") ?? "";
  const tab: Tab = status === "deleted" || (TABS as string[]).includes(status) ? (status as Tab) : "submitted";
  const setTab = (t: Tab) => setParams((p) => { p.set("status", t); return p; }, { replace: true });
  const [lists, setLists] = useState<Partial<Record<ReviewStatus, Receipt[]>>>({});
  const [deletions, setDeletions] = useState<Deletion[] | null>(null);
  const [owner, setOwner] = useState("");
  const [confirm, setConfirm] = useState<string | null>(null); // a receipt id, a log key, or "all-logs"
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    Promise.all([
      ...TABS.map((s) => admin.receipts(s).then((r) => [s, r.items] as const)),
    ]).then((pairs) => setLists(Object.fromEntries(pairs)), (e) => setError(e.message));
  const loadDeletions = () => admin.deletions().then((r) => setDeletions(r.items), (e) => setError(e.message));

  useEffect(() => {
    load();
    loadDeletions();
  }, []);

  async function remove(id: string) {
    setBusy(true);
    setError(null);
    try {
      await admin.deleteReceipt(id);
      setConfirm(null);
      await Promise.all([load(), loadDeletions()]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function removeLog(key: string | null) {
    setBusy(true);
    setError(null);
    try {
      await (key ? admin.deleteDeletion(key) : admin.clearDeletions());
      setConfirm(null);
      await loadDeletions();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const all = tab === "deleted" ? [] : lists[tab] ?? [];
  const owners = [...new Set(Object.values(lists).flat().map((r) => r.owner_name))].sort();
  const items = all
    .filter((r) => !owner || r.owner_name === owner)
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>증빙 관리</h1>
          <p>모든 상태의 증빙을 보고, 필요하면 영구 삭제해요. 삭제하면 사진·대화·처리 이력까지 지워지고 삭제 기록만 남아요.</p>
        </div>
      </div>
      {error && <div className="alert error">{error}</div>}

      <div className="tabs" role="tablist">
        {TABS.map((s) => (
          <button key={s} role="tab" aria-selected={tab === s} onClick={() => setTab(s)}>
            {REVIEW_LABEL[s]}<span className="count">{lists[s]?.length ?? 0}</span>
          </button>
        ))}
        <button role="tab" aria-selected={tab === "deleted"} onClick={() => setTab("deleted")}>
          삭제 기록<span className="count">{deletions?.length ?? 0}</span>
        </button>
      </div>

      {tab === "deleted" && !!deletions?.length && (
        <div className="filters">
          <span className="muted small">삭제 기록은 누가·언제 무엇을 지웠는지만 남겨요.</span>
          <span className="spacer" />
          {confirm === "all-logs" ? (
            <>
              <span className="small">삭제 기록 {deletions.length}건을 모두 지울까요?</span>
              <button className="btn btn-danger btn-sm" disabled={busy} onClick={() => removeLog(null)}>모두 지우기</button>
              <button className="btn btn-ghost btn-sm" onClick={() => setConfirm(null)}>취소</button>
            </>
          ) : (
            <button className="btn btn-ghost btn-sm" onClick={() => setConfirm("all-logs")}>모두 지우기</button>
          )}
        </div>
      )}
      {tab !== "deleted" && (
        <div className="filters">
          <select value={owner} onChange={(e) => setOwner(e.target.value)} aria-label="직원">
            <option value="">모든 직원</option>
            {owners.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
          <span className="muted small">최근에 바뀐 순</span>
        </div>
      )}

      <section className="panel">
        {tab === "deleted" ? (
          !deletions ? <div className="empty">불러오는 중…</div> : deletions.length === 0 ? (
            <div className="empty">삭제한 증빙이 없어요.</div>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>삭제 일시</th><th>삭제한 사람</th><th>제출자</th><th>상호명</th><th className="num">총액</th><th>삭제 전 상태</th><th /></tr></thead>
                <tbody>
                  {deletions.map((d) => (
                    <tr key={d.key}>
                      <td className="small">{shortDate(d.deleted_at)}</td>
                      <td>{d.deleted_by}</td>
                      <td>{d.owner_name ?? "—"}</td>
                      <td>{d.merchant_name ?? "(분석 전)"}</td>
                      <td className="num">{won(d.total_amount)}</td>
                      <td>{d.review_status ? <ReviewChip status={d.review_status} /> : "—"}</td>
                      <td className="row-actions">
                        {confirm === d.key ? (
                          <>
                            <button className="btn btn-danger btn-sm" disabled={busy} onClick={() => removeLog(d.key)}>지우기</button>
                            <button className="btn btn-ghost btn-sm" onClick={() => setConfirm(null)}>취소</button>
                          </>
                        ) : (
                          <button className="btn btn-ghost btn-sm" onClick={() => setConfirm(d.key)}>지우기</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : lists[tab] === undefined ? <div className="empty">불러오는 중…</div> : items.length === 0 ? (
          <div className="empty">{REVIEW_LABEL[tab]} 상태의 증빙이 없어요.</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>제출자</th><th>상호명</th><th>거래 일시</th><th className="num">총액</th><th>상태</th><th>마지막 변경</th><th /></tr></thead>
              <tbody>
                {items.map((r) => (
                  <tr key={r.id}>
                    <td>{r.owner_name}<span className="muted small"> {r.fields.department ?? ""}</span></td>
                    <td><b>{r.fields.merchant_name ?? "(분석 전)"}</b></td>
                    <td>{txDate(r.fields.transaction_at)}</td>
                    <td className="num">{won(r.fields.total_amount)}</td>
                    <td><ReviewChip status={r.review_status} /></td>
                    <td className="small muted">{shortDate(r.updated_at)}</td>
                    <td className="row-actions">
                      {confirm === r.id ? (
                        <>
                          <span className="small">영구 삭제할까요?</span>
                          <button className="btn btn-danger btn-sm" disabled={busy} onClick={() => remove(r.id)}>
                            {busy ? "삭제 중…" : "삭제"}
                          </button>
                          <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => setConfirm(null)}>취소</button>
                        </>
                      ) : (
                        <button className="btn btn-ghost btn-sm" onClick={() => setConfirm(r.id)}>삭제</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
