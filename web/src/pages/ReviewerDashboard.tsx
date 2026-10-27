import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, downloadCsv, type Me, type Receipt, type ReviewStatus } from "../api";
import RecentReceipts, { openedRows } from "../components/RecentReceipts";
import { flagLevel, ReviewFlags } from "../components/ReviewFlags";
import { AmountBars, lastMonths, monthLabel, sumBy, Widget } from "../components/Widget";
import { laterIds, reviewOrder } from "../later";
import { compareSubmissionTime } from "../reviewOrder";
import { categoryLabel, won } from "../labels";

const thisMonth = () => new Date().toISOString().slice(0, 7);
const daysAgo = (iso?: string | null) => (iso ? Math.floor((Date.now() - Date.parse(iso)) / 86_400_000) : 0);
const waited = (iso?: string | null) => (daysAgo(iso) === 0 ? "오늘" : `${daysAgo(iso)}일째`);
const oldestNote = (iso?: string | null) => (daysAgo(iso) === 0 ? "가장 오래된 건 오늘 제출" : `가장 오래된 건 ${daysAgo(iso)}일째`);

type Sort = "oldest" | "amount";
const SORTS: { key: Sort; label: string }[] = [
  { key: "oldest", label: "오래된 순" },
  { key: "amount", label: "금액 큰 순" },
];

/** Reviewer home: a summary strip, the queue as the main table, recents, and this month's approvals. */
export default function ReviewerDashboard({ me }: { me: Me }) {
  const [lists, setLists] = useState<Partial<Record<ReviewStatus, Receipt[]>>>({});
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<Sort>("oldest");
  const navigate = useNavigate();

  useEffect(() => {
    const statuses: ReviewStatus[] = ["submitted", "changes_requested", "approved"];
    Promise.all(statuses.map((s) => api.reviewList(s).then((r) => [s, r.items] as const))).then(
      (pairs) => setLists(Object.fromEntries(pairs)),
      (e) => setError(e.message),
    );
  }, []);

  const loading = lists.submitted === undefined;
  const order = reviewOrder(lists.submitted ?? []); // the order [검토 시작] walks through
  const later = laterIds();
  const oldest = order.length ? [...order].sort(compareSubmissionTime)[0] : null;
  const flagged = order.filter(flagLevel);
  const sentBack = lists.changes_requested ?? [];
  const approved = (lists.approved ?? []).filter((r) => (r.reviewed_at ?? "").startsWith(thisMonth()));
  const total = approved.reduce((n, r) => n + (r.fields.total_amount ?? 0), 0);
  const known = Object.values(lists).flat();
  const handled = [...(lists.approved ?? []), ...sentBack]
    .filter((r) => r.reviewed_by === me.name)
    .sort((a, b) => (b.reviewed_at ?? "").localeCompare(a.reviewed_at ?? ""));

  const queue =
    sort === "amount" ? [...order].sort((a, b) => (b.fields.total_amount ?? 0) - (a.fields.total_amount ?? 0)) : order;

  const summary = [
    { label: "검토 대기", value: order.length, note: oldest ? oldestNote(oldest.submitted_at) : "없음",
      tone: oldest && daysAgo(oldest.submitted_at) >= 3 ? "warn" : undefined, to: "/review?status=submitted" },
    { label: "주의·오류", value: flagged.length, note: `대기 ${order.length}건 중`,
      tone: flagged.length ? "warn" : undefined, to: "/review?status=flagged" },
    { label: "보완 요청 중", value: sentBack.length, note: "직원 수정 대기", to: "/review?status=changes_requested" },
    { label: "이번 달 승인", value: approved.length, note: won(total), to: "/review?status=approved" },
  ] as const;

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>홈</h1>
          <p>{loading ? "불러오는 중…" : order.length ? `${me.name}님, 검토할 증빙이 ${order.length}건 있어요.` : "검토할 증빙이 없어요."}</p>
        </div>
        <button className="btn btn-primary btn-lg" disabled={!order.length}
          onClick={() => navigate(`/review/${order[0].id}`, { state: { from: "/" } })}>
          검토 시작 →
        </button>
      </div>
      {error && <div className="alert error">{error}</div>}

      <section className="summary-strip" aria-label="요약">
        {summary.map((m) => {
          const body = (
            <>
              <span className="metric-label">{m.label}</span>
              <span className={`metric-value${"tone" in m && m.tone ? ` ${m.tone}` : ""}`}>{loading ? "–" : m.value}</span>
              <span className="metric-note">{loading ? "" : m.note}</span>
            </>
          );
          return <Link key={m.label} to={m.to} className="summary-item">{body}</Link>;
        })}
      </section>

      <div className="dash-grid">
        <Widget title="검토 대기열" span={8} info="review_points" action={<Link to="/review" className="btn btn-pill">전체 목록</Link>}>
          <div className="tabs tabs-sm" role="tablist">
            {SORTS.map((s) => (
              <button key={s.key} role="tab" aria-selected={sort === s.key} onClick={() => setSort(s.key)}>{s.label}</button>
            ))}
          </div>
          {loading ? <div className="muted small">불러오는 중…</div> : queue.length === 0 ? (
            <div className="muted small">검토할 증빙이 없어요.</div>
          ) : (
            <table className="table queue-table">
              <thead>
                <tr>
                  <th>제출자</th>
                  <th>상호명</th>
                  <th className="num">총액</th>
                  <th>검토 포인트</th>
                  <th className="num">기다림</th>
                </tr>
              </thead>
              <tbody>
                {queue.slice(0, 8).map((r) => (
                  <tr key={r.id} className={`row${flagLevel(r) ? ` flag-${flagLevel(r)}` : ""}`}
                    onClick={() => navigate(`/review/${r.id}`, { state: { from: "/" } })}>
                    <td>
                      {r.owner_name}
                      <span className="muted small"> {r.fields.department ?? ""}</span>
                    </td>
                    <td><Link to={`/review/${r.id}`} state={{ from: "/" }} onClick={(e) => e.stopPropagation()}><b>{r.fields.merchant_name ?? "—"}</b></Link></td>
                    <td className="num">{won(r.fields.total_amount)}</td>
                    <td><ReviewFlags receipt={r} later={later.has(r.id)} /></td>
                    <td className={`num small${daysAgo(r.submitted_at) >= 3 ? " warn-text" : " muted"}`}>{waited(r.submitted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {queue.length > 8 && <div className="muted small" style={{ marginTop: 8 }}>외 {queue.length - 8}건 — 전체 목록에서 봐요.</div>}
        </Widget>

        <RecentReceipts title="최근 본 증빙" span={4} loading={loading} showOwner link={(r) => `/review/${r.id}`}
          tabs={[
            { label: "최근 본", rows: openedRows(known, true), empty: "아직 열어 본 증빙이 없어요." },
            { label: "내가 처리한", rows: handled, empty: "아직 처리한 증빙이 없어요." },
          ]} />

        <Widget title="이번 달 승인 — 분류별" span={4} info="categories"
          action={<button className="btn btn-pill" onClick={() => downloadCsv(thisMonth(), "approved").catch((e) => setError(e.message))}>정산용 CSV</button>}>
          <AmountBars rows={sumBy(approved, (r) => categoryLabel(r.fields.category), (r) => r.fields.total_amount)} />
        </Widget>

        <Widget title="이번 달 승인 — 부서별" span={4}>
          <AmountBars rows={sumBy(approved, (r) => r.fields.department, (r) => r.fields.total_amount)} />
        </Widget>

        <Widget title="월별 승인" span={4} action={<span className="muted small">최근 6개월</span>}>
          <AmountBars rows={lastMonths(6).map((m) => ({
            label: monthLabel(m),
            amount: (lists.approved ?? []).filter((r) => (r.reviewed_at ?? "").startsWith(m))
              .reduce((n, r) => n + (r.fields.total_amount ?? 0), 0),
          }))} />
        </Widget>
      </div>
    </main>
  );
}
