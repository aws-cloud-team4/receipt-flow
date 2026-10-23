import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, type Me, type Receipt } from "../api";
import RecentReceipts, { openedRows } from "../components/RecentReceipts";
import { AnalysisChip, ReviewChip } from "../components/StatusChip";
import { AmountBars, lastMonths, monthLabel, sumBy, Widget } from "../components/Widget";
import { categoryLabel, won } from "../labels";

const thisMonth = () => new Date().toISOString().slice(0, 7);

/** Employee home in the reviewer-home layout: a summary strip, what needs doing as the main table,
 * recents, and this month by category / by month with a quick start. */
export default function EmployeeDashboard({ me }: { me: Me }) {
  const [items, setItems] = useState<Receipt[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.mine().then((r) => setItems(r.items), (e) => setError(e.message));
  }, []);

  const loading = items === null;
  const all = items ?? [];
  const by = (s: Receipt["review_status"]) => all.filter((r) => r.review_status === s);
  const sentBack = by("changes_requested");
  const drafts = by("draft");
  const waiting = by("submitted");
  const month = all.filter((r) => (r.fields.transaction_at ?? "").startsWith(thisMonth()) && r.review_status !== "draft");
  const approvedThisMonth = all.filter((r) => r.review_status === "approved" && (r.reviewed_at ?? "").startsWith(thisMonth()));
  const total = (rs: Receipt[]) => rs.reduce((n, r) => n + (r.fields.total_amount ?? 0), 0);
  const todo = [...sentBack, ...drafts];

  const summary = [
    { label: "보완 요청", value: sentBack.length, note: sentBack.length ? "고쳐서 다시 제출" : "없음",
      tone: sentBack.length ? "err" : undefined, to: "/receipts?status=changes_requested" },
    { label: "작성 중", value: drafts.length, note: "제출 전", to: "/receipts?status=draft" },
    { label: "검토 중", value: waiting.length, note: "담당자 확인 대기", to: "/receipts?status=submitted" },
    { label: "이번 달 승인", value: approvedThisMonth.length, note: won(total(approvedThisMonth)), to: "/receipts?status=approved" },
  ];

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>홈</h1>
          <p>
            {loading ? "불러오는 중…" : sentBack.length ? `보완 요청이 ${sentBack.length}건 있어요. 먼저 확인해 주세요.`
              : drafts.length ? `작성 중인 증빙이 ${drafts.length}건 있어요.`
              : `${me.name}님, 영수증을 찍어 올리면 AI가 정리해 드려요.`}
          </p>
        </div>
        <Link to="/new" className="btn btn-primary btn-lg">+ 영수증 올리기</Link>
      </div>
      {error && <div className="alert error">{error}</div>}

      <section className="summary-strip" aria-label="요약">
        {summary.map((m) => (
          <Link key={m.label} to={m.to} className="summary-item">
            <span className="metric-label">{m.label}</span>
            <span className={`metric-value${m.tone ? ` ${m.tone}` : ""}`}>{loading ? "–" : m.value}</span>
            <span className="metric-note">{loading ? "" : m.note}</span>
          </Link>
        ))}
      </section>

      <div className="dash-grid">
        <Widget title="할 일" span={8} action={<Link to="/receipts" className="btn btn-pill">내 증빙 전체</Link>}>
          {loading ? <div className="muted small">불러오는 중…</div> : todo.length === 0 ? (
            <div className="todo-empty">
              <b>할 일이 없어요</b>
              <span className="muted small">보완 요청이나 작성 중인 증빙이 생기면 여기에 보여요.</span>
              <Link to="/new" className="btn btn-pill">+ 영수증 올리기</Link>
            </div>
          ) : (
            <table className="table queue-table todo-table">
              <thead>
                <tr><th>상태</th><th>상호명</th><th className="num">총액</th><th>안내</th><th /></tr>
              </thead>
              <tbody>
                {todo.slice(0, 8).map((r) => {
                  const back = r.review_status === "changes_requested";
                  return (
                    <tr key={r.id} className={`row${back ? " flag-error" : ""}`} onClick={() => navigate(`/receipts/${r.id}`)}>
                      <td><ReviewChip status={r.review_status} /></td>
                      <td><b>{r.fields.merchant_name ?? "(분석 전)"}</b></td>
                      <td className="num">{won(r.fields.total_amount)}</td>
                      <td className="todo-note">
                        {back ? <span title={r.review_note ?? ""}>{r.review_note ?? "담당자가 돌려보냈어요"}</span>
                          : <AnalysisChip status={r.analysis_status} />}
                      </td>
                      <td className="num">
                        <Link to={`/receipts/${r.id}`} className="btn btn-pill btn-sm" onClick={(e) => e.stopPropagation()}>
                          {back ? "고치기" : "이어서"}
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
          {todo.length > 8 && <div className="muted small" style={{ marginTop: 8 }}>외 {todo.length - 8}건 — 내 증빙에서 봐요.</div>}
        </Widget>

        <RecentReceipts title="최근 증빙" span={4} loading={loading} link={(r) => `/receipts/${r.id}`}
          tabs={[
            { label: "최근 연", rows: openedRows(all, false), empty: "아직 열어 본 증빙이 없어요." },
            { label: "최근 올린", rows: all, empty: "아직 올린 증빙이 없어요." },
          ]} />

        <Widget title="이번 달 내 지출 — 분류별" span={4} info="categories">
          <div className="metric-pair">
            <div><div className="metric-label">제출한 금액</div><b className="metric-value">{won(total(month))}</b></div>
            <div><div className="metric-label">건수</div><b className="metric-value">{month.length}</b></div>
          </div>
          <div style={{ marginTop: 12 }}>
            <AmountBars rows={sumBy(month, (r) => categoryLabel(r.fields.category), (r) => r.fields.total_amount)} />
          </div>
        </Widget>

        <Widget title="월별 지출" span={4} action={<span className="muted small">최근 6개월</span>}>
          <AmountBars rows={lastMonths(6).map((m) => ({
            label: monthLabel(m),
            amount: total(all.filter((r) => r.review_status !== "draft" && (r.fields.transaction_at ?? "").startsWith(m))),
          }))} />
        </Widget>

        <Widget title="빠른 시작" span={4}>
          <div className="quick">
            <Link to="/new" className="quick-item">
              <b>영수증 올리기</b>
              <span>카드 영수증을 찍으면 AI가 읽고, 목적·분류를 함께 정해 드려요.</span>
            </Link>
            <Link to="/receipts" className="quick-item">
              <b>내 증빙 전체</b>
              <span>상태·분류로 거르고, 상호·금액으로 검색해요.</span>
            </Link>
            <Link to="/me" className="quick-item">
              <b>내 프로필</b>
              <span>부서·직급 확인, 비밀번호 변경</span>
            </Link>
          </div>
        </Widget>
      </div>
    </main>
  );
}
