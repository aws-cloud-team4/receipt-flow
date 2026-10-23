import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Receipt, type ReviewStatus } from "../api";
import { InfoLink } from "../components/Help";
import SearchBox from "../components/SearchBox";
import { SubNav } from "../components/Shell";
import { matches } from "../search";
import { AnalysisChip, ReviewChip } from "../components/StatusChip";
import { CATEGORIES, categoryLabel, REVIEW_LABEL, shortDate, txDate, won } from "../labels";

const TABS: (ReviewStatus | "all")[] = ["all", "draft", "changes_requested", "submitted", "approved"];

export default function EmployeeHome() {
  const [items, setItems] = useState<Receipt[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // tab, category and search live in the address (the home screen links straight to a tab)
  const [params, setParams] = useSearchParams();
  // the list as it is now (tab, filters), so "← 내 증빙으로" on a receipt comes back to it
  const here = `/receipts${params.toString() ? `?${params}` : ""}`;
  const status = params.get("status");
  const tab = (TABS as string[]).includes(status ?? "") ? (status as ReviewStatus) : "all";
  const setParam = (k: string) => (v: string) =>
    setParams((p) => { if (v && v !== "all") p.set(k, v); else p.delete(k); return p; }, { replace: true });
  const setTab = (s: ReviewStatus | "all") => setParam("status")(s);
  const category = params.get("cat") ?? "";
  const query = params.get("q") ?? "";
  const filtering = !!(category || query);
  const clearFilters = () => setParams((p) => { p.delete("cat"); p.delete("q"); return p; }, { replace: true });
  const navigate = useNavigate();

  useEffect(() => {
    api.mine().then((r) => setItems(r.items), (e) => setError(e.message));
  }, []);

  const filtered = useMemo(
    () => (items ?? []).filter((r) => (!category || r.fields.category === category) && matches(r, query)),
    [items, category, query],
  );
  const count = (s: ReviewStatus | "all") => filtered.filter((r) => s === "all" || r.review_status === s).length;
  const shown = filtered.filter((r) => tab === "all" || r.review_status === tab);
  const todo = count("draft") + count("changes_requested");

  return (
    <>
      <SubNav items={[{ label: "홈", to: "/" }, { label: "내 증빙" }]} />
      <main className="page">
        <div className="page-head">
          <div>
            <h1>내 증빙<InfoLink topic="status" /></h1>
            <p>{todo > 0 ? `처리할 증빙이 ${todo}건 있어요.` : "영수증을 찍어 올리면 AI가 정리해 드려요."}</p>
          </div>
          <Link to="/new" className="btn btn-primary btn-lg">
            + 영수증 올리기
          </Link>
        </div>

        <div className="tabs" role="tablist">
          {TABS.map((s) => (
            <button key={s} role="tab" aria-selected={tab === s} onClick={() => setTab(s)}>
              {s === "all" ? "전체" : REVIEW_LABEL[s]}
              <span className="count">{count(s)}</span>
            </button>
          ))}
        </div>

        <div className="filters">
          <select value={category} onChange={(e) => setParam("cat")(e.target.value)} aria-label="지출 분류">
            <option value="">모든 분류</option>
            {Object.entries(CATEGORIES).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select>
          <SearchBox value={query} onChange={setParam("q")} placeholder="상호·금액·목적·승인번호·날짜" />
          <span className="muted small">최근 순</span>
        </div>

        {error && <div className="alert error">{error}</div>}
        <section className="panel">
          {items === null ? (
            <div className="empty">불러오는 중…</div>
          ) : shown.length === 0 ? (
            <div className="empty">{filtering ? (
              <>검색 결과가 없어요.<div className="empty-actions"><button className="btn btn-ghost btn-sm" onClick={clearFilters}>필터 지우기</button></div></>
            ) : "증빙이 없습니다."}</div>
          ) : (
            <>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>상호명</th>
                      <th>거래 일시</th>
                      <th className="num">총액</th>
                      <th>분류</th>
                      <th>지출 목적</th>
                      <th>분석</th>
                      <th>상태</th>
                      <th>수정</th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((r) => (
                      <tr key={r.id} className="row" onClick={() => navigate(`/receipts/${r.id}`, { state: { from: here } })}>
                        <td><b>{r.fields.merchant_name ?? "(분석 전)"}</b></td>
                        <td>{txDate(r.fields.transaction_at)}</td>
                        <td className="num">{won(r.fields.total_amount)}</td>
                        <td>{categoryLabel(r.fields.category)}</td>
                        <td>{r.fields.purpose ?? "—"}</td>
                        <td><AnalysisChip status={r.analysis_status} /></td>
                        <td><ReviewChip status={r.review_status} /></td>
                        <td className="muted small">{shortDate(r.updated_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="cards">
                {shown.map((r) => (
                  <Link key={r.id} to={`/receipts/${r.id}`} state={{ from: here }} className="card-row">
                    <div className="main">
                      <div className="title">{r.fields.merchant_name ?? "(분석 전)"}</div>
                      <div className="muted small">
                        {txDate(r.fields.transaction_at)} · {categoryLabel(r.fields.category)} · {r.fields.purpose ?? "목적 미입력"}
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div className="amount">{won(r.fields.total_amount)}</div>
                      <ReviewChip status={r.review_status} />
                    </div>
                  </Link>
                ))}
              </div>
            </>
          )}
        </section>
      </main>
    </>
  );
}
