// Mini screens for the two role cards: the employee's phone and the reviewer's queue window.
// Small HTML mock-ups in the app's own style (sample values only).

export function EmployeeArt() {
  return (
    <div className="role-art employee" aria-hidden>
      <div className="ra-phone">
        <div className="ra-top"><span className="ra-brand">receipt<i>flow</i></span></div>
        <div className="ra-body">
          <div className="ra-title">내 할 일</div>
          <div className="ra-metrics">
            <span><b className="err">0</b>보완 요청</span>
            <span><b>1</b>작성 중</span>
            <span><b>2</b>검토 중</span>
          </div>
          <div className="ra-receipt">
            <span className="ra-thumb" />
            <span className="ra-lines">
              <b>한빛 김밥천국</b>
              <i>35,500원 · AI가 읽는 중</i>
              <span className="ra-progress"><span /></span>
            </span>
          </div>
          <div className="ra-cta">+ 영수증 올리기</div>
        </div>
      </div>
    </div>
  );
}

export function ReviewerArt() {
  const rows = [
    { who: "김직원", where: "한빛 김밥천국", amount: "35,500", flag: "warn" },
    { who: "이직원", where: "카카오T 블루", amount: "23,400", flag: "" },
    { who: "박직원", where: "알파문구", amount: "29,200", flag: "err" },
  ];
  return (
    <div className="role-art reviewer" aria-hidden>
      <div className="ra-window">
        <div className="ra-bar"><i /><i /><i /><span>검토 대기열</span></div>
        <div className="ra-table">
          {rows.map((r) => (
            <div key={r.who} className={`ra-row ${r.flag}`}>
              <span>{r.who}</span>
              <b>{r.where}</b>
              <span className="num">{r.amount}</span>
              <span className={`ra-chip ${r.flag}`}>{r.flag === "err" ? "오류 1" : r.flag === "warn" ? "주의 1" : "—"}</span>
            </div>
          ))}
        </div>
        <div className="ra-actions">
          <span className="ghost">건너뛰기</span>
          <span className="danger">보완 요청</span>
          <span className="ok">승인</span>
        </div>
      </div>
    </div>
  );
}
