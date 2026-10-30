import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { devProfiles, type DevProfile } from "../api";
import {
  AuthError,
  authMode,
  completeNewPassword,
  PASSWORD_RULE,
  passwordProblem,
  rememberedEmail,
  rememberEmail,
  signIn,
  signInDev,
  type Role,
} from "../auth";

type Step = { kind: "credentials" } | { kind: "new_password"; session: string };

// Layout follows the AWS console sign-in page: centered wordmark, sign-in card on the left,
// a promo panel on the right, light patterned background. Branding and copy are our own.
// Accounts are created by an admin with a temporary password; the first sign-in sets a new one.
export default function Login({ onSignedIn }: { onSignedIn: () => Promise<void> }) {
  const [step, setStep] = useState<Step>({ kind: "credentials" });
  const [email, setEmail] = useState(rememberedEmail);
  const [remember, setRemember] = useState(() => rememberedEmail() !== "");
  const [password, setPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [devOpen, setDevOpen] = useState(false);
  const navigate = useNavigate();

  async function finish() {
    rememberEmail(remember ? email.trim() : null);
    await onSignedIn();
    navigate("/", { replace: true });
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function submitCredentials(e: FormEvent) {
    e.preventDefault();
    run(async () => {
      const result = await signIn(email.trim(), password);
      if (result.status === "new_password_required") {
        setPassword("");
        setStep({ kind: "new_password", session: result.session });
        return;
      }
      await finish();
    });
  }

  function submitNewPassword(e: FormEvent) {
    e.preventDefault();
    if (step.kind !== "new_password") return;
    const problem = passwordProblem(newPassword) ?? (newPassword !== confirm ? "두 비밀번호가 달라요." : null);
    if (problem) {
      setError(problem);
      return;
    }
    run(async () => {
      try {
        await completeNewPassword(email.trim(), newPassword, step.session);
      } catch (err) {
        if (err instanceof AuthError && err.code === "NotAuthorizedException") {
          // The challenge session lasts only a few minutes.
          setStep({ kind: "credentials" });
          throw new Error("시간이 지나 처음부터 다시 해야 해요. 임시 비밀번호로 다시 로그인해 주세요.");
        }
        throw err;
      }
      await finish();
    });
  }

  function backToStart() {
    setStep({ kind: "credentials" });
    setNewPassword("");
    setConfirm("");
    setError(null);
  }

  async function dev(role: Role, id: string) {
    signInDev(role, id);
    await finish();
  }

  const passwordType = showPassword ? "text" : "password";
  const showToggle = (
    <label className="signin-check">
      <input type="checkbox" checked={showPassword} onChange={(e) => setShowPassword(e.target.checked)} />
      비밀번호 표시
    </label>
  );

  let card;
  if (step.kind === "new_password") {
    card = (
      <>
        <h1 id="signin-title">새 비밀번호 설정</h1>
        <p className="signin-sub">처음 로그인하셨네요. 임시 비밀번호 대신 쓸 비밀번호를 정해 주세요.</p>
        <form className="signin-form" onSubmit={submitNewPassword}>
          <div className="field">
            <label htmlFor="new-email">이메일</label>
            <input id="new-email" type="email" autoComplete="username" value={email} readOnly disabled />
          </div>
          <div className="field">
            <label htmlFor="new-password">새 비밀번호</label>
            <input id="new-password" type={passwordType} autoComplete="new-password" value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)} required autoFocus />
          </div>
          <div className="field">
            <label htmlFor="new-password-confirm">새 비밀번호 확인</label>
            <input id="new-password-confirm" type={passwordType} autoComplete="new-password" value={confirm}
              onChange={(e) => setConfirm(e.target.value)} required />
          </div>
          <p className="signin-hint">{PASSWORD_RULE}</p>
          {showToggle}
          {error && <div className="alert error" role="alert">{error}</div>}
          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? "저장 중…" : "비밀번호 저장하고 시작"}
          </button>
          <button type="button" className="btn btn-outline btn-block" disabled={busy} onClick={backToStart}>
            처음으로
          </button>
        </form>
      </>
    );
  } else if (authMode === "dev" || devOpen) {
    card = (
      <>
        <h1 id="signin-title">{authMode === "dev" ? "로그인" : "개발자 로그인"}</h1>
        <p className="signin-sub">테스트 계정을 골라 비밀번호 없이 들어가요. (이 PC의 개발 서버에서만)</p>
        <DevPicker onPick={(p) => dev(p.role, p.id)} />
        {authMode !== "dev" && (
          <button type="button" className="link-btn signin-back" onClick={() => setDevOpen(false)}>← 일반 로그인</button>
        )}
      </>
    );
  } else {
    card = (
      <>
        <h1 id="signin-title">로그인</h1>
        <p className="signin-sub">직원·담당자 계정으로 로그인하세요.</p>
        <form className="signin-form" onSubmit={submitCredentials}>
          <div className="field">
            <label htmlFor="email">이메일</label>
            <input id="email" type="email" autoComplete="username" value={email}
              onChange={(e) => setEmail(e.target.value)} required autoFocus={!email} />
          </div>
          <div className="field">
            <label htmlFor="password">비밀번호</label>
            <input id="password" type={passwordType} autoComplete="current-password" value={password}
              onChange={(e) => setPassword(e.target.value)} required autoFocus={!!email} />
          </div>
          <div className="signin-row">
            {showToggle}
            <label className="signin-check">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              이메일 기억
            </label>
          </div>
          {error && <div className="alert error" role="alert">{error}</div>}
          <button className="btn btn-primary btn-block" disabled={busy}>
            {busy ? "로그인 중…" : "로그인"}
          </button>
          <div className="signin-divider"><span>계정이 없거나 비밀번호를 잊으셨나요?</span></div>
          <p className="signin-help">계정과 임시 비밀번호는 관리자가 발급해 드립니다.</p>
        </form>
      </>
    );
  }

  return (
    <div className="signin">
      <header className="signin-logo">
        <Link to="/" className="brand" aria-label="receiptflow 소개로">
          receipt<span>flow</span>
        </Link>
      </header>

      <main className="signin-main">
        <div className="signin-left">
          <section className="signin-card" aria-labelledby="signin-title">
            {card}
          </section>
          {/* developer login: only in the local dev server build (never in a deploy build) */}
          {import.meta.env.DEV && authMode !== "dev" && !devOpen && (
            <button type="button" className="link-btn signin-dev" onClick={() => setDevOpen(true)}>개발자 모드</button>
          )}
        </div>

        <aside className="signin-promo" aria-label="서비스 소개">
          <div className="promo-inner">
            <p className="promo-eyebrow">receiptflow</p>
            <h2>
              영수증은 찍어서 올리세요.
              <br />
              정리는 AI가 도와드려요.
            </h2>
            <ol className="promo-steps">
              <li><b>찍어서 올리기</b> 테두리를 맞추면 AI가 상호명·일시·금액을 읽어요.</li>
              <li><b>확인하고 답하기</b> 읽은 내용을 확인하면 AI가 지출 목적과 분류를 추천해요.</li>
              <li><b>직접 제출하기</b> 최종 확인 후 제출하면 검수 담당자가 승인하거나 보완을 요청해요.</li>
            </ol>
          </div>
        </aside>
      </main>

      <footer className="signin-footer">© 2026 receiptflow · AWS 클라우드 AI 부트캠프 4팀</footer>
    </div>
  );
}

const ROLE_ORDER = ["employee", "reviewer", "admin"] as const;

/** The test accounts from the server, grouped by role; one click signs in. */
function DevPicker({ onPick }: { onPick: (p: DevProfile) => void }) {
  const [items, setItems] = useState<DevProfile[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    devProfiles().then(setItems, (e: Error) =>
      setError(e.message === "off" ? "개발자 로그인이 꺼져 있어요. services/.env에 RF_DEV_LOGIN=true를 넣고 백엔드를 다시 켜 주세요." : e.message));
  }, []);
  if (error) return <div className="alert error">{error}</div>;
  if (!items) return <div className="muted small">불러오는 중…</div>;
  return (
    <div className="dev-picker">
      {ROLE_ORDER.map((role) => {
        const group = items.filter((p) => p.role === role);
        if (!group.length) return null;
        return (
          <div key={role} className="dev-group">
            <div className="dev-group-title">{group[0].role_label}</div>
            {group.map((p) => (
              <button key={p.id} type="button" className="dev-account" onClick={() => onPick(p)}>
                <b>{p.name}</b>
                <span>{[p.department, p.position, p.employee_no].filter(Boolean).join(" · ")}</span>
              </button>
            ))}
          </div>
        );
      })}
    </div>
  );
}
