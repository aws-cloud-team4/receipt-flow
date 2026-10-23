import type { ReactNode } from "react";
import { InfoLink, type HelpTopic } from "./Help";

/** A home-screen card in the console-home style: title, optional action, body, optional footer. */
export function Widget({ title, info, action, footer, span = 4, children }: {
  title: string;
  /** A "정보" link next to the title that opens this help topic. */
  info?: HelpTopic;
  action?: ReactNode;
  footer?: ReactNode;
  /** Columns out of 12 on a wide screen (one column on a phone). */
  span?: 3 | 4 | 5 | 6 | 7 | 8 | 12;
  children: ReactNode;
}) {
  return (
    <section className={`widget w-${span}`}>
      <div className="widget-head">
        <h2>{title}{info && <InfoLink topic={info} />}</h2>
        {action}
      </div>
      <div className="widget-body">{children}</div>
      {footer && <div className="widget-foot">{footer}</div>}
    </section>
  );
}

/** A label with a big number on the left and a short note on the right (like an "open issues" row). */
export function MetricRow({ label, value, note, tone, onClick }: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "err" | "warn";
  onClick?: () => void;
}) {
  return (
    <div className={`metric-row${onClick ? " clickable" : ""}`} onClick={onClick}
      role={onClick ? "button" : undefined} tabIndex={onClick ? 0 : undefined}
      onKeyDown={(e) => onClick && e.key === "Enter" && onClick()}>
      <div className="metric-label">{label}</div>
      <div className="metric-line">
        <span className={`metric-value${tone ? ` ${tone}` : ""}`}>{value}</span>
        {note && <span className="metric-note">{note}</span>}
      </div>
    </div>
  );
}

/** Horizontal bars for amounts by group (category, department). */
export function AmountBars({ rows }: { rows: { label: string; amount: number }[] }) {
  if (!rows.length) return <div className="muted small">아직 없어요.</div>;
  const max = Math.max(...rows.map((r) => r.amount), 1);
  return (
    <div className="bars">
      {rows.map((r) => (
        <div key={r.label} className="bar-row">
          <span className="bar-label">{r.label}</span>
          <span className="bar-track"><span className="bar-fill" style={{ width: `${(r.amount / max) * 100}%` }} /></span>
          <span className="bar-amount">{r.amount.toLocaleString("ko-KR")}원</span>
        </div>
      ))}
    </div>
  );
}

/** Sum amounts by a key, largest first. */
export function sumBy<T>(items: T[], key: (t: T) => string | null | undefined, amount: (t: T) => number | null | undefined) {
  const totals = new Map<string, number>();
  for (const it of items) {
    const k = key(it);
    if (!k) continue;
    totals.set(k, (totals.get(k) ?? 0) + (amount(it) ?? 0));
  }
  return [...totals.entries()].map(([label, value]) => ({ label, amount: value })).sort((a, b) => b.amount - a.amount);
}

/** "YYYY-MM" for this month and the n-1 before it, oldest first. */
export const lastMonths = (n: number) =>
  Array.from({ length: n }, (_, i) => {
    const d = new Date();
    d.setDate(1);
    d.setMonth(d.getMonth() - (n - 1 - i));
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  });

/** "10월" from "2026-10". */
export const monthLabel = (m: string) => `${Number(m.slice(5))}월`;
