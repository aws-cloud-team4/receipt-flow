import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { Me } from "../api";

type Item = { label: string; path: string; status?: string; isDefault?: boolean };
type Group = { title?: string; items: Item[] };

/** Shortcuts to every list tab, by role. A tab is `path?status=…`; `isDefault` marks the tab a bare path opens. */
function groupsFor(role: Me["role"]): Group[] {
  if (role === "admin")
    return [
      { items: [{ label: "계정 관리", path: "/" }] },
      {
        title: "증빙 관리",
        items: [
          { label: "작성 중", path: "/admin/receipts", status: "draft" },
          { label: "제출", path: "/admin/receipts", status: "submitted", isDefault: true },
          { label: "보완 요청", path: "/admin/receipts", status: "changes_requested" },
          { label: "승인", path: "/admin/receipts", status: "approved" },
          { label: "삭제 기록", path: "/admin/receipts", status: "deleted" },
        ],
      },
      { items: [{ label: "내 프로필", path: "/me" }] },
    ];
  if (role === "reviewer")
    return [
      { items: [{ label: "홈", path: "/" }] },
      {
        title: "검수 목록",
        items: [
          { label: "제출", path: "/review", status: "submitted", isDefault: true },
          { label: "주의", path: "/review", status: "flagged" },
          { label: "보완 요청", path: "/review", status: "changes_requested" },
          { label: "승인", path: "/review", status: "approved" },
        ],
      },
      { items: [{ label: "내 프로필", path: "/me" }] },
    ];
  return [
    { items: [{ label: "홈", path: "/" }, { label: "영수증 올리기", path: "/new" }] },
    {
      title: "내 증빙",
      items: [
        { label: "전체", path: "/receipts", isDefault: true },
        { label: "작성 중", path: "/receipts", status: "draft" },
        { label: "보완 요청", path: "/receipts", status: "changes_requested" },
        { label: "제출", path: "/receipts", status: "submitted" },
        { label: "승인", path: "/receipts", status: "approved" },
      ],
    },
    { items: [{ label: "내 프로필", path: "/me" }] },
  ];
}

const KEY = "rf.sidebar";
const narrow = () => window.matchMedia("(max-width: 760px)").matches;

/** Open/closed state of the side menu: folded by default; wide screens remember the choice, and on a
 * phone a pick closes it. */
export function useSideMenu() {
  const [open, setOpen] = useState(() => {
    try {
      return !narrow() && localStorage.getItem(KEY) === "open";
    } catch {
      return false;
    }
  });
  const { pathname, search } = useLocation();

  const set = (next: boolean) => {
    setOpen(next);
    if (!narrow()) {
      try {
        localStorage.setItem(KEY, next ? "open" : "closed");
      } catch {
        // storage blocked: the menu just isn't remembered
      }
    }
  };

  useEffect(() => {
    if (narrow()) setOpen(false);
  }, [pathname, search]);

  return { open, set, toggle: () => set(!open) };
}

/** The round menu button at the left of the bar under the logo (filled blue while the menu is open). */
export function MenuButton({ open, onClick }: { open: boolean; onClick: () => void }) {
  return (
    <button className={`menu-btn${open ? " on" : ""}`} onClick={onClick} aria-expanded={open}
      aria-label={open ? "메뉴 닫기" : "메뉴 열기"} title={open ? "메뉴 닫기" : "메뉴 열기"}>
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.2"
        strokeLinecap="round" aria-hidden><path d="M5 7h14M5 12h14M5 17h14" /></svg>
    </button>
  );
}

/** Console-style side menu: a title with a close arrow, then the tab shortcuts for this role. */
export default function Sidebar({ me, onClose }: { me: Me; onClose: () => void }) {
  const { pathname, search } = useLocation();
  const status = new URLSearchParams(search).get("status");
  const active = (it: Item) =>
    pathname === it.path && (it.status ? status === it.status || (!!it.isDefault && !status) : !status);

  return (
    <>
      <aside className="sidebar" aria-label="바로가기">
        <div className="side-head">
          <b>{me.role_label} 메뉴</b>
          <button className="side-close" onClick={onClose} aria-label="메뉴 닫기" title="메뉴 닫기">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M15 6l-6 6 6 6" /></svg>
          </button>
        </div>
        <nav className="side-nav">
          {groupsFor(me.role).map((g, i) => (
            <div key={g.title ?? i} className="side-group">
              {g.title && <div className="side-title">{g.title}</div>}
              {g.items.map((it) => (
                <Link key={it.label + (it.status ?? "")} to={it.status ? `${it.path}?status=${it.status}` : it.path}
                  className={`side-link${g.title ? " sub" : ""}${active(it) ? " on" : ""}`}
                  aria-current={active(it) ? "page" : undefined}>
                  {it.label}
                </Link>
              ))}
            </div>
          ))}
        </nav>
      </aside>
      <div className="side-scrim" onClick={onClose} aria-hidden />
    </>
  );
}
