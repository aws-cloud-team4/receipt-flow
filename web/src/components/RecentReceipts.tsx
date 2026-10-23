import { useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import type { Receipt } from "../api";
import { won } from "../labels";
import { recentOpened } from "../recent";
import { ReviewChip } from "./StatusChip";
import { Widget } from "./Widget";

export interface RecentTab {
  label: string;
  rows: Receipt[];
  empty: string;
}

/** Receipts this person opened lately, newest first, with their current state from `known`.
 * `keepUnknown`: also list ones not in `known` (a reviewer's lists are partial; an employee's are not). */
export function openedRows(known: Receipt[], keepUnknown: boolean): Receipt[] {
  const byId = new Map(known.map((r) => [r.id, r]));
  return recentOpened().flatMap((e) => {
    const r = byId.get(e.id);
    if (r) return [r];
    return keepUnknown ? [{ id: e.id, fields: { merchant_name: e.merchant } } as Receipt] : [];
  });
}

/** A home widget with tabs of receipt lists (recently opened / uploaded / handled). */
export default function RecentReceipts({ title, tabs, link, loading, showOwner, span = 5, action }: {
  title: string;
  tabs: RecentTab[];
  link: (r: Receipt) => string;
  loading: boolean;
  showOwner?: boolean;
  span?: 4 | 5;
  action?: ReactNode;
}) {
  // start on the first tab that has something
  const [picked, setPicked] = useState<number | null>(null);
  const here = useLocation().pathname;
  const current = picked ?? Math.max(0, tabs.findIndex((t) => t.rows.length > 0));
  const tab = tabs[current];

  return (
    <Widget title={title} span={span} action={action}>
      <div className="tabs tabs-sm" role="tablist">
        {tabs.map((t, i) => (
          <button key={t.label} role="tab" aria-selected={i === current} onClick={() => setPicked(i)}>
            {t.label}
          </button>
        ))}
      </div>
      {loading ? <div className="muted small">불러오는 중…</div> : tab.rows.length === 0 ? (
        <div className="muted small">{tab.empty}</div>
      ) : (
        <ul className="link-list">
          {tab.rows.slice(0, 7).map((r) => (
            <li key={r.id}>
              <Link to={link(r)} state={{ from: here }}>{r.fields.merchant_name ?? "(분석 전)"}</Link>
              <span className="muted small">
                {[showOwner ? r.owner_name : null, r.fields.total_amount != null ? won(r.fields.total_amount) : null]
                  .filter(Boolean).join(" · ")}
              </span>
              {r.review_status ? <ReviewChip status={r.review_status} /> : <span />}
            </li>
          ))}
        </ul>
      )}
    </Widget>
  );
}
