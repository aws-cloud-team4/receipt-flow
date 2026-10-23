import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { api, downloadCsv, type Receipt, type ReviewStatus } from "../api";
import { InfoLink } from "../components/Help";
import { flagLevel as level, ReviewFlags } from "../components/ReviewFlags";
import SearchBox from "../components/SearchBox";
import { SubNav } from "../components/Shell";
import { matches } from "../search";
import { laterIds } from "../later";
import { compareSubmissionTime } from "../reviewOrder";
import { CATEGORIES, categoryLabel, REVIEW_LABEL, shortDate, txDate, won } from "../labels";

const STATUSES: ReviewStatus[] = ["submitted", "changes_requested", "approved"];
// 주의: submitted receipts with an error or warning review point (a view of 제출, not a status)
type Tab = ReviewStatus | "flagged";
const TABS: Tab[] = ["submitted", "flagged", "changes_requested", "approved"];
const TAB_LABEL = (t: Tab) => (t === "flagged" ? "주의" : REVIEW_LABEL[t]);

export default function ReviewHome() {
  // the status tab lives in the address, so the home screen can link straight to it
  const [params, setParams] = useSearchParams();
  const tab = (TABS as string[]).includes(params.get("status") ?? "") ? (params.get("status") as Tab) : "submitted";
  const setTab = (s: Tab) => setParams((p) => { p.set("status", s); return p; }, { replace: true });
  // filters live in the address too, so "← 목록으로" comes back to the same view
  const setParam = (k: string) => (v: string) =>
    setParams((p) => { if (v) p.set(k, v); else p.delete(k); return p; }, { replace: true });
  const dept = params.get("dept") ?? "";
  const category = params.get("cat") ?? "";
  const query = params.get("q") ?? "";
  const clearFilters = () => setParams((p) => { p.delete("dept"); p.delete("cat"); p.delete("q"); return p; }, { replace: true });
  const [departments, setDepartments] = useState<string[]>([]);
  const later = laterIds();
  const [lists, setLists] = useState<Partial<Record<ReviewStatus, Receipt[]>>>({});
  const [error, setError] = useState<string | null>(null);
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const navigate = useNavigate();
  const here = useLocation();
  const back = { from: here.pathname + here.search }; // the detail page returns here

  useEffect(() => {
    Promise.all(STATUSES.map((s) => api.reviewList(s).then((r) => [s, r.items] as const))).then(
      (pairs) => setLists(Object.fromEntries(pairs)),
      (e) => setError(e.message),
    );
    api.meta().then((m) => setDepartments(m.departments.map((d) => d.name)), () => {});
  }, []);

  const listFor = (t: Tab) => (t === "flagged" ? lists.submitted?.filter((r) => level(r)) : lists[t]);
  // First in, first out: the oldest submission comes first; warnings are highlighted, not moved up.
  const all = [...(listFor(tab) ?? [])].sort(compareSubmissionTime);
  const items = listFor(tab) && all.filter((r) =>
    (!dept || r.fields.department === dept) && (!category || r.fields.category === category) && matches(r, query));
  // every department, with how many of this tab's receipts it has (older values on receipts too)
  const depts = [...new Set([...departments, ...all.map((r) => r.fields.department).filter(Boolean) as string[]])];
  const perDept = (d: string) => all.filter((r) => r.fields.department === d).length;
  const filtering = !!(dept || category || query);
  const flags = (r: Receipt) => <ReviewFlags receipt={r} later={(tab === "submitted" || tab === "flagged") && later.has(r.id)} />;

  return (
    <>
      <SubNav items={[{ label: "홈", to: "/" }, { label: "검수 목록" }]} />
      <main className="page">
        <div className="page-head">
          <div>
            <h1>검수 목록<InfoLink topic="status" /></h1>
            <p>제출된 증빙을 확인하고 승인하거나 보완을 요청하세요.</p>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} aria-label="내보낼 월"
              className="btn btn-ghost" style={{ fontWeight: 500 }} />
            <button className="btn btn-blue" onClick={() => downloadCsv(month).catch((e) => setError(e.message))}>
              CSV 내보내기
            </button>
          </div>
        </div>

        <div className="tabs" role="tablist">
          {TABS.map((s) => (
            <button key={s} role="tab" aria-selected={tab === s} onClick={() => setTab(s)}>
              {TAB_LABEL(s)}
              <span className={`count${s === "flagged" && listFor(s)?.length ? " warn-count" : ""}`}>{listFor(s)?.length ?? 0}</span>
            </button>
          ))}
        </div>

        <div className="filters">
          <select value={dept} onChange={(e) => setParam("dept")(e.target.value)} aria-label="부서">
            <option value="">모든 부서</option>
            {depts.map((d) => <option key={d} value={d}>{d} ({perDept(d)})</option>)}
          </select>
          <select value={category} onChange={(e) => setParam("cat")(e.target.value)} aria-label="지출 분류">
            <option value="">모든 분류</option>
            {Object.entries(CATEGORIES).map(([code, label]) => <option key={code} value={code}>{label}</option>)}
          </select>
          <SearchBox value={query} onChange={setParam("q")} placeholder="제출자·사번·상호·금액·승인번호" />
          <span className="muted small">먼저 제출된 순</span>
        </div>

        {error && <div className="alert error">{error}</div>}
        <section className="panel">
          {!items ? (
            <div className="empty">불러오는 중…</div>
          ) : items.length === 0 ? (
            <div className="empty">{all.length && filtering ? (
              <>검색 결과가 없어요.<div className="empty-actions"><button className="btn btn-ghost btn-sm" onClick={clearFilters}>필터 지우기</button></div></>
            ) : all.length ? "조건에 맞는 증빙이 없습니다." : tab === "flagged" ? "주의·오류가 있는 검토 대기 증빙이 없습니다." : `${REVIEW_LABEL[tab]} 상태의 증빙이 없습니다.`}</div>
          ) : (
            <>
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>제출자</th>
                      <th>상호명</th>
                      <th>거래 일시</th>
                      <th className="num">총액</th>
                      <th>부서</th>
                      <th>분류</th>
                      <th>검토 포인트</th>
                      <th>제출</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((r) => (
                      <tr key={r.id} className={`row${level(r) ? ` flag-${level(r)}` : ""}`}
                        onClick={() => navigate(`/review/${r.id}`, { state: back })}>
                        <td>
                          {r.owner_name}
                          {r.owner_profile?.position && <span className="muted small"> {r.owner_profile.position}</span>}
                        </td>
                        <td><b>{r.fields.merchant_name}</b></td>
                        <td>{txDate(r.fields.transaction_at)}</td>
                        <td className="num">{won(r.fields.total_amount)}</td>
                        <td>{r.fields.department ?? "—"}</td>
                        <td>{categoryLabel(r.fields.category)}</td>
                        <td>{flags(r)}</td>
                        <td className="muted small">{shortDate(r.submitted_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="cards">
                {items.map((r) => (
                  <Link key={r.id} to={`/review/${r.id}`} state={back} className={`card-row${level(r) ? ` flag-${level(r)}` : ""}`}>
                    <div className="main">
                      <div className="title">{r.fields.merchant_name}</div>
                      <div className="muted small">{r.owner_name} · {r.fields.department} · {categoryLabel(r.fields.category)} · {txDate(r.fields.transaction_at)}</div>
                      <div style={{ marginTop: 4 }}>{flags(r)}</div>
                    </div>
                    <div className="amount">{won(r.fields.total_amount)}</div>
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
