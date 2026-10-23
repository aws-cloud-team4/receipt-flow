import { useEffect, useState, type FormEvent } from "react";
import { admin, type Account, type AccountRole, type Me, type OrgOptions } from "../api";

const statusLabel = (a: Account) =>
  !a.enabled ? "사용 중지" : a.status === "FORCE_CHANGE_PASSWORD" ? "첫 로그인 대기" : a.status === "CONFIRMED" ? "사용 중" : a.status;

type Form = { mode: "new" } | { mode: "edit"; account: Account };

/** Admin home: every account in the user pool; create, edit, issue a temporary password, disable. */
export default function AdminUsers({ me }: { me: Me }) {
  const [items, setItems] = useState<Account[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [secret, setSecret] = useState<{ who: string; password: string; created: boolean } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const load = () => admin.users().then((r) => setItems(r.items), (e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  async function run(key: string, action: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const isMe = (a: Account) => a.sub === me.sub || (a.email ?? "").toLowerCase() === me.email.toLowerCase();
  const pending = (items ?? []).filter((a) => a.enabled && a.status === "FORCE_CHANGE_PASSWORD").length;

  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>계정 관리</h1>
          <p>{items ? `계정 ${items.length}개${pending ? ` · 첫 로그인 대기 ${pending}개` : ""}` : "불러오는 중…"}</p>
        </div>
        <button className="btn btn-primary btn-lg" onClick={() => setForm({ mode: "new" })}>+ 새 계정</button>
      </div>
      {error && <div className="alert error">{error}</div>}

      <section className="panel">
        {!items ? <div className="empty">불러오는 중…</div> : items.length === 0 ? (
          <div className="empty">계정이 없어요.</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>이름</th><th>이메일</th><th>사번</th><th>부서</th><th>직급</th><th>역할</th><th>상태</th><th />
                </tr>
              </thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.username} className={a.enabled ? "" : "muted-row"}>
                    <td><b>{a.name ?? "—"}</b>{isMe(a) && <span className="muted small"> (나)</span>}</td>
                    <td className="small">{a.email}</td>
                    <td>{a.employee_no ?? "—"}</td>
                    <td>{a.department ?? "—"}</td>
                    <td>{a.position ?? "—"}</td>
                    <td><span className={`role-pill ${a.role}`}>{a.role_label}</span></td>
                    <td className="small">{statusLabel(a)}</td>
                    <td className="row-actions">
                      <button className="btn btn-ghost btn-sm" onClick={() => setForm({ mode: "edit", account: a })}>수정</button>
                      <button className="btn btn-ghost btn-sm" disabled={busy !== null}
                        onClick={() => run(`pw-${a.username}`, async () => {
                          const r = await admin.resetPassword(a.username);
                          setSecret({ who: a.name ?? a.email ?? a.username, password: r.temporary_password, created: false });
                          await load();
                        })}>
                        임시 비밀번호
                      </button>
                      {!isMe(a) && (
                        <button className={`btn btn-sm ${a.enabled ? "btn-danger" : "btn-ghost"}`} disabled={busy !== null}
                          onClick={() => run(`en-${a.username}`, async () => {
                            await admin.setEnabled(a.username, !a.enabled);
                            await load();
                          })}>
                          {a.enabled ? "사용 중지" : "다시 사용"}
                        </button>
                      )}
                      {!isMe(a) && (confirmDelete === a.username ? (
                        <>
                          <span className="small">계정을 영구 삭제할까요?</span>
                          <button className="btn btn-danger btn-sm" disabled={busy !== null}
                            onClick={() => run(`del-${a.username}`, async () => {
                              await admin.deleteUser(a.username);
                              setConfirmDelete(null);
                              await load();
                            })}>
                            삭제
                          </button>
                          <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(null)}>취소</button>
                        </>
                      ) : (
                        <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDelete(a.username)}>삭제</button>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {form && (
        <AccountDialog
          form={form}
          self={form.mode === "edit" && isMe(form.account)}
          onClose={() => setForm(null)}
          onSaved={async (password, who) => {
            setForm(null);
            if (password) setSecret({ who, password, created: true });
            await load();
          }}
        />
      )}
      {secret && <SecretDialog {...secret} onClose={() => setSecret(null)} />}
    </main>
  );
}

const ROLE_CARDS: { value: AccountRole; label: string; desc: string }[] = [
  { value: "employee", label: "직원", desc: "영수증을 올리고 제출해요" },
  { value: "reviewer", label: "검수 담당자", desc: "증빙을 검토하고 승인해요 · 재무회계부" },
  { value: "admin", label: "관리자", desc: "계정과 증빙을 관리해요 · 부서 없음" },
];

function AccountDialog({ form, self, onClose, onSaved }: {
  form: Form;
  self: boolean;
  onClose: () => void;
  onSaved: (temporaryPassword: string | null, who: string) => Promise<void>;
}) {
  const a = form.mode === "edit" ? form.account : null;
  const [opts, setOpts] = useState<OrgOptions | null>(null);
  const [v, setV] = useState({
    email: a?.email ?? "",
    name: a?.name ?? "",
    department: a?.department ?? "",
    position: a?.position ?? "",
    role: (a?.role ?? "employee") as AccountRole,
  });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) =>
    setV((x) => ({ ...x, [k]: e.target.value }));

  useEffect(() => {
    admin.options().then(setOpts, (e) => setError(e.message));
  }, []);

  // 검수 담당자 belong to accounting (set and locked); admins have no department
  const isAdmin = v.role === "admin";
  const lockedDept = v.role === "reviewer" ? opts?.reviewer_department : undefined;
  const department = isAdmin ? "" : lockedDept ?? v.department;
  const pickRole = (role: AccountRole) => setV((x) => ({ ...x, role }));
  const known = new Set(opts?.departments.map((x) => x.name) ?? []);
  const deptInfo = opts?.departments.find((x) => x.name === department);
  const ready = !!opts && !!v.email && !!v.name && !!v.position && (isAdmin || !!department);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (a) {
        await admin.updateUser(a.username, { name: v.name, position: v.position, role: v.role, ...(isAdmin ? {} : { department }) });
        await onSaved(null, v.name);
      } else {
        const r = await admin.createUser({ email: v.email, name: v.name, position: v.position, role: v.role, ...(isAdmin ? {} : { department }) });
        await onSaved(r.temporary_password, `${v.name} (${r.user.employee_no})`);
      }
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="dialog-backdrop" onClick={onClose}>
      <form className="dialog account-dialog" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <header className="acc-head">
          <div>
            <h2>{a ? "계정 수정" : "새 계정 만들기"}</h2>
            <p className="muted small">
              {a ? <>사번 <b>{a.employee_no ?? "—"}</b> · 사번은 바뀌지 않아요</> : "만들면 임시 비밀번호가 한 번 보여요. 직접 전달해 주세요."}
            </p>
          </div>
          <button type="button" className="help-close" onClick={onClose} aria-label="닫기">✕</button>
        </header>

        <section className="acc-section">
          <div className="acc-section-title">역할</div>
          <div className="role-cards" role="radiogroup" aria-label="역할">
            {ROLE_CARDS.map((r) => (
              <button key={r.value} type="button" role="radio" aria-checked={v.role === r.value}
                className={`role-card ${r.value}${v.role === r.value ? " on" : ""}`}
                disabled={self && r.value !== v.role} onClick={() => pickRole(r.value)}>
                <b>{r.label}</b>
                <span>{r.desc}</span>
              </button>
            ))}
          </div>
          {self && <p className="muted small">자기 자신의 역할은 바꿀 수 없어요.</p>}
        </section>

        <section className="acc-section">
          <div className="acc-section-title">기본 정보</div>
          <div className="form-grid">
            <div className="field full">
              <label htmlFor="acc-email">이메일 <span className="req">*</span></label>
              <input id="acc-email" type="email" required value={v.email} onChange={set("email")} disabled={!!a}
                autoComplete="off" placeholder="name@company.com" autoFocus={!a} />
              {!a && <span className="field-hint">로그인할 때 아이디로 써요</span>}
            </div>
            <div className="field full">
              <label htmlFor="acc-name">이름 <span className="req">*</span></label>
              <input id="acc-name" required maxLength={50} value={v.name} onChange={set("name")} placeholder="홍길동" />
            </div>
          </div>
        </section>

        <section className="acc-section">
          <div className="acc-section-title">소속</div>
          <div className="form-grid">
            {!isAdmin && (
              <div className="field">
                <label htmlFor="acc-dept">부서 <span className="req">*</span></label>
                <select id="acc-dept" required value={department} onChange={set("department")} disabled={!opts || !!lockedDept}>
                  <option value="" disabled>부서 선택</option>
                  {a?.department && !known.has(a.department) && <option value={a.department}>{a.department} (이전 값)</option>}
                  {opts?.departments.map((x) => <option key={x.code} value={x.name}>{x.name}</option>)}
                </select>
                <span className="field-hint">
                  {lockedDept ? `검수 담당자는 ${lockedDept} 소속이에요` : deptInfo ? `${deptInfo.code} · ${deptInfo.description}` : " "}
                </span>
              </div>
            )}
            <div className={`field${isAdmin ? " full" : ""}`}>
              <label htmlFor="acc-pos">직급 <span className="req">*</span></label>
              <select id="acc-pos" required value={v.position} onChange={set("position")} disabled={!opts}>
                <option value="" disabled>직급 선택</option>
                {a?.position && opts && !opts.positions.includes(a.position) && <option value={a.position}>{a.position} (이전 값)</option>}
                {opts?.positions.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
              {isAdmin && <span className="field-hint">관리자는 부서 없이 관리 업무만 해요</span>}
            </div>
          </div>
        </section>

        {error && <div className="alert error">{error}</div>}
        <footer className="dialog-actions acc-foot">
          <span className="muted small">{a ? "바뀐 정보는 다음 로그인 때 반영돼요" : "사번은 자동으로 정해져요"}</span>
          <span className="spacer" />
          <button type="button" className="btn btn-ghost" onClick={onClose}>취소</button>
          <button type="submit" className="btn btn-primary" disabled={busy || !ready}>{busy ? "저장 중…" : a ? "저장" : "계정 만들기"}</button>
        </footer>
      </form>
    </div>
  );
}

function SecretDialog({ who, password, created, onClose }: { who: string; password: string; created: boolean; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="dialog-backdrop">
      <div className="dialog admin-dialog" role="alertdialog" aria-labelledby="secret-title">
        <h2 id="secret-title">{created ? "계정을 만들었어요" : "임시 비밀번호를 새로 만들었어요"}</h2>
        <p>{who}님의 임시 비밀번호예요. 첫 로그인 때 새 비밀번호를 정하게 돼요.</p>
        <div className="secret-box">
          <code>{password}</code>
          <button className="btn btn-blue btn-sm" onClick={() => navigator.clipboard?.writeText(password).then(() => setCopied(true))}>
            {copied ? "복사됨" : "복사"}
          </button>
        </div>
        <div className="alert warn"><b>주의</b> 이 창을 닫으면 다시 볼 수 없어요. 필요하면 임시 비밀번호를 새로 만들면 돼요.</div>
        <div className="dialog-actions">
          <button className="btn btn-primary" onClick={onClose}>확인</button>
        </div>
      </div>
    </div>
  );
}
