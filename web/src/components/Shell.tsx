import { createContext, useContext, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, NavLink } from "react-router-dom";
import type { Me } from "../api";
import { useHelp } from "./Help";
import Sidebar, { MenuButton, useSideMenu } from "./Sidebar";

// where a page's breadcrumbs go: the bar under the logo, next to the menu button
const CrumbSlot = createContext<HTMLElement | null>(null);

export default function Shell({ me, onLogout, children }: { me: Me; onLogout: () => void; children: ReactNode }) {
  const menu = useSideMenu();
  const help = useHelp();
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand" aria-label="receiptflow 홈">
          receipt<span>flow</span>
        </Link>
        <nav className="topnav" aria-label="메뉴">
          <NavLink to="/" end>{me.role === "admin" ? "계정 관리" : "홈"}</NavLink>
          {me.role === "admin" ? <NavLink to="/admin/receipts">증빙 관리</NavLink>
            : me.role === "reviewer" ? <NavLink to="/review">검수 목록</NavLink> : <NavLink to="/receipts">내 증빙</NavLink>}
        </nav>
        <div className="spacer" />
        <Link to="/me" className="who" title="내 프로필">
          <span className="who-name">{me.name}</span>
          <span className="who-meta">{[me.position, me.department].filter(Boolean).join(" · ")}</span>
          <span className="role-tag">{me.role_label}</span>
        </Link>
        <button className="link" onClick={onLogout}>
          로그아웃
        </button>
      </header>
      <div className="toolbar">
        <MenuButton open={menu.open} onClick={menu.toggle} />
        <div className="crumbs" ref={setSlot} />
        <button className="toolbar-info" onClick={() => help.open("status")} aria-label="도움말: 상태" title="도움말">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2"
            strokeLinecap="round" aria-hidden><circle cx="12" cy="12" r="9" /><path d="M12 11v6M12 7.5v.5" /></svg>
        </button>
      </div>
      <div className="app-body">
        {menu.open && <Sidebar me={me} onClose={() => menu.set(false)} />}
        <div className="app-main"><CrumbSlot.Provider value={slot}>{children}</CrumbSlot.Provider></div>
      </div>
    </>
  );
}

/** A page's breadcrumbs, shown in the bar under the logo. */
export function SubNav({ items }: { items: { label: string; to?: string }[] }) {
  const slot = useContext(CrumbSlot);
  if (!slot) return null;
  return createPortal(
    <nav className="subnav" aria-label="현재 위치">
      {items.map((item, i) => (
        <span key={item.label} className="crumb">
          {i > 0 && (
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M9 6l6 6-6 6" /></svg>
          )}
          {item.to ? <Link to={item.to}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}
        </span>
      ))}
    </nav>,
    slot,
  );
}
