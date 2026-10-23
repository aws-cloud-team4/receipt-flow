import { useState, type FormEvent } from "react";
import type { Me } from "../api";
import { authMode, changePassword, isDevSession, PASSWORD_RULE, passwordProblem } from "../auth";
import { SubNav } from "../components/Shell";

/** Read-only login profile plus the user's own password change. Profile fields are registered by an admin. */
export default function Profile({ me }: { me: Me }) {
  const rows: [string, string | null][] = [
    ["이름", me.name],
    ["직원코드", me.employee_no],
    ["부서", me.department],
    ["직급", me.position],
    ["권한", me.role_label],
    ["이메일", me.email],
  ];
  return (
    <>
      <SubNav items={[{ label: "내 프로필" }]} />
      <main className="page stack" style={{ gap: 16 }}>
        <section className="panel profile-card">
          <div className="panel-body stack" style={{ gap: 18 }}>
            <div className="profile-head">
              <div className="avatar-lg" aria-hidden>{me.name.slice(0, 1)}</div>
              <div>
                <h1>{me.name}</h1>
                <p className="muted">{[me.position, me.department].filter(Boolean).join(" · ") || "부서 정보 없음"}</p>
              </div>
            </div>
            <dl className="kv">
              {rows.map(([label, value]) => (
                <div key={label} style={{ display: "contents" }}>
                  <dt>{label}</dt>
                  <dd>{value || "—"}</dd>
                </div>
              ))}
            </dl>
            {!me.department && <div className="alert warn">부서가 등록되지 않았어요. 관리자에게 문의해 주세요.</div>}
            <p className="muted small">
              이름·부서·직급은 관리자가 관리해요. 바꿀 내용이 있으면 관리자에게 요청해 주세요. 비밀번호는 아래에서 직접 바꿀 수 있어요.
              증빙에는 작성할 때의 부서·직급이 기록됩니다.
            </p>
          </div>
        </section>
        {authMode === "cognito" && !isDevSession() ? <PasswordChange /> : (
          <section className="panel profile-card">
            <div className="panel-head"><h2>비밀번호 변경</h2></div>
            <div className="panel-body">
              <p className="muted small">개발자 모드 테스트 계정은 비밀번호가 없어서 바꿀 수 없어요. 실제 계정으로 로그인하면 여기서 바꿀 수 있어요.</p>
            </div>
          </section>
        )}
      </main>
    </>
  );
}

function PasswordChange() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const problem =
      passwordProblem(next) ??
      (next !== confirm ? "새 비밀번호 두 칸이 달라요." : null) ??
      (next === current ? "지금 비밀번호와 다른 비밀번호를 정해 주세요." : null);
    if (problem) {
      setMessage({ kind: "error", text: problem });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await changePassword(current, next);
      setCurrent("");
      setNext("");
      setConfirm("");
      setMessage({ kind: "ok", text: "비밀번호를 바꿨어요. 다음 로그인부터 새 비밀번호를 쓰세요." });
    } catch (err) {
      setMessage({ kind: "error", text: (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel profile-card">
      <div className="panel-head"><h2>비밀번호 변경</h2></div>
      <form className="panel-body stack" style={{ gap: 12 }} onSubmit={submit}>
        <div className="field">
          <label htmlFor="pw-current">현재 비밀번호</label>
          <input id="pw-current" type="password" autoComplete="current-password" value={current}
            onChange={(e) => setCurrent(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="pw-next">새 비밀번호</label>
          <input id="pw-next" type="password" autoComplete="new-password" value={next}
            onChange={(e) => setNext(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="pw-confirm">새 비밀번호 확인</label>
          <input id="pw-confirm" type="password" autoComplete="new-password" value={confirm}
            onChange={(e) => setConfirm(e.target.value)} required />
        </div>
        <p className="muted small">{PASSWORD_RULE}</p>
        {message && <div className={`alert ${message.kind === "ok" ? "ok" : "error"}`} role="status">{message.text}</div>}
        <div>
          <button className="btn btn-primary" disabled={busy}>{busy ? "바꾸는 중…" : "비밀번호 바꾸기"}</button>
        </div>
      </form>
    </section>
  );
}
