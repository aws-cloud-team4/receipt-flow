import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import type { Me } from "../api";

/**
 * The account menu at the right of the top bar, like the console's: the name opens a dark panel with the
 * profile (employee number can be copied), then [내 프로필] and [로그아웃] as the console's pill buttons
 * (서비스 소개 stays in the side menu only).
 * Closes on a click outside, Escape, or moving to another page.
 */
export default function AccountMenu({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const escape = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked (http, permissions): the number is still on screen to select */
    }
  }

  const rows: [string, string | null][] = [
    ["부서", me.department],
    ["직급", me.position],
    ["역할", me.role_label],
  ];

  return (
    <div className="account" ref={box}>
      <button className={`who${open ? " on" : ""}`} onClick={() => setOpen((v) => !v)}
        aria-haspopup="true" aria-expanded={open} title="계정 메뉴">
        <span className="who-name">{me.name}</span>
        <span className="role-tag">{me.role_label}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
          strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M6 9l6 6 6-6" /></svg>
      </button>
      {open && (
        <div className="account-menu" role="menu" aria-label="계정">
          <dl>
            <div className="account-row"><dt>이름</dt><dd>{me.name}</dd></div>
            {me.employee_no && (
              <div className="account-row">
                <dt>사번</dt>
                <dd>
                  <button className="account-copy" onClick={() => copy(me.employee_no!)} title="사번 복사">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                      strokeLinejoin="round" aria-hidden><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></svg>
                    {me.employee_no}
                  </button>
                  {copied && <span className="account-copied" role="status">복사됨</span>}
                </dd>
              </div>
            )}
            {rows.filter(([, v]) => v).map(([k, v]) => (
              <div key={k} className="account-row"><dt>{k}</dt><dd>{v}</dd></div>
            ))}
          </dl>
          <hr />
          <div className="account-foot">
            <Link to="/me" className="account-profile" role="menuitem">내 프로필</Link>
            <button className="account-logout" onClick={onLogout} role="menuitem">로그아웃</button>
          </div>
        </div>
      )}
    </div>
  );
}
