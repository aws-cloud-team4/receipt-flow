import { useEffect, useState } from "react";

type Usage = {
  label: string;
  spent: number;
  limit: number;
  remaining: number;
  percent: number;
  start: string | null;
  end: string | null;
  days_left: number | null;
  as_of: string;
};

const usd = (n: number) => `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const STATUS = { ok: "여유 있어요", warn: "주의해서 써요", danger: "예산이 거의 다 찼어요" };

const md = (iso: string) => {
  const d = new Date(iso);
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
};

/** "AWS 비용" section of the landing page: the team's spend against its budget
 * (GET /api/public/usage, a daily 09:00 snapshot from AWS Budgets).
 * The section is in the page from the start (so the scroll-in reveal sees it); the numbers fill in. */
export default function UsageSection() {
  const [usage, setUsage] = useState<Usage | null | "error">(null);

  useEffect(() => {
    fetch("/api/public/usage")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setUsage, () => setUsage("error"));
  }, []);

  const u = usage && usage !== "error" ? usage : null;
  const level = u ? (u.percent >= 90 ? "danger" : u.percent >= 70 ? "warn" : "ok") : "ok";
  const dash = "—";

  return (
    <section id="cost" className="lp-wrap lp-section">
      <h2 className="reveal">AWS 비용</h2>
      <p className="lp-lead reveal">데모데이까지 정해진 예산 안에서 운영해요. 매일 오전 9시 AWS Budgets 기준이에요.</p>
      <div className={`lp-usage reveal ${level}`} aria-live="polite">
        <div className="lp-usage-main">
          <span className="lp-chip lp-usage-chip">{u ? `${md(u.as_of)} 오전 9시 기준` : "매일 오전 9시 기준"}</span>
          <h3>{u?.label ?? "AWS 클라우드 4조"} 사용량</h3>
          <div className="lp-usage-spent">
            <strong>{u ? usd(u.spent) : dash}</strong>
            <span>/ {u ? usd(u.limit) : dash}</span>
          </div>
          <div className="lp-usage-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={u?.percent ?? 0}>
            <span style={{ width: `${Math.min(u?.percent ?? 0, 100)}%` }} />
          </div>
          <p className="lp-usage-note">
            {usage === "error"
              ? "지금은 사용량을 불러올 수 없어요."
              : u
                ? <>
                    {u.start && u.end ? `${md(u.start)} ~ ${md(u.end)}` : ""}
                    <span className={`lp-usage-status ${level}`}>{STATUS[level]}</span>
                  </>
                : "불러오는 중…"}
          </p>
        </div>
        <div className="lp-usage-tiles">
          <div className="lp-usage-tile">
            <span>남은 금액</span>
            <b>{u ? usd(u.remaining) : dash}</b>
          </div>
          <div className="lp-usage-tile">
            <span>사용률</span>
            <b>{u ? `${u.percent}%` : dash}</b>
          </div>
          <div className="lp-usage-tile">
            <span>데모데이까지</span>
            <b>{u?.days_left != null ? `${u.days_left}일` : dash}</b>
          </div>
        </div>
      </div>
    </section>
  );
}
