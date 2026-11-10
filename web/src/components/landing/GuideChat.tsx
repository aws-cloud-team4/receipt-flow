import { useEffect, useRef, useState, type FormEvent } from "react";

/**
 * "receiptflow에 물어보기": a floating chat on the intro page that answers questions about the service
 * from the project documents (`POST /guide/ask`, its own pod — not the employees' AI assistant).
 * No login. The server limits questions per visitor and per day and says so in the error message.
 */

interface Source { file: string; title: string }
interface Line { role: "user" | "assistant"; text: string; sources?: Source[]; error?: boolean } // sources: kept, not shown

const STARTERS = [
  "receiptflow는 어떤 서비스인가요?",
  "영수증 한 장은 어떻게 처리되나요?",
  "AI가 잘못 읽으면 어떻게 되나요?",
  "어떤 AWS 서비스를 썼나요?",
];

async function ask(question: string, history: Line[], onText: (t: string) => void): Promise<Source[]> {
  const resp = await fetch("/guide/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      history: history.filter((l) => !l.error).slice(-6).map(({ role, text }) => ({ role, text: text.slice(0, 1500) })),
    }),
  });
  if (!resp.ok || !resp.body) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.error?.message ?? "지금은 답변할 수 없어요. 잠시 뒤 다시 물어봐 주세요.");
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sources: Source[] = [];
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const event = /^event: (.*)$/m.exec(block)?.[1];
      const data = JSON.parse(/^data: (.*)$/m.exec(block)?.[1] ?? "{}");
      if (event === "delta") onText(data.text ?? "");
      else if (event === "done") sources = data.sources ?? [];
      else if (event === "error") throw new Error(data.message);
    }
  }
  return sources;
}

/** Plain text with **bold** (the model sometimes marks key phrases); everything else stays text. */
function Rich({ text }: { text: string }) {
  return <>{text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <b key={i}>{part.slice(2, -2)}</b>
      : part.length > 2 && part.startsWith("`") && part.endsWith("`") ? <code key={i}>{part.slice(1, -1)}</code>
      : part)}</>;
}

export default function GuideChat() {
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [lines, open]);

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const history = lines;
    setText("");
    setBusy(true);
    setLines([...history, { role: "user", text: q }, { role: "assistant", text: "" }]);
    const update = (patch: (last: Line) => Line) =>
      setLines((ls) => [...ls.slice(0, -1), patch(ls[ls.length - 1])]);
    try {
      const sources = await ask(q, history, (t) => update((l) => ({ ...l, text: l.text + t })));
      update((l) => ({ ...l, sources }));
    } catch (e) {
      update(() => ({ role: "assistant", text: (e as Error).message, error: true }));
    } finally {
      setBusy(false);
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    send(text);
  }

  return (
    <>
      {!open && (
        <button className="lp-guide-fab" onClick={() => setOpen(true)} aria-label="receiptflow에 물어보기">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
            <path d="M4 5h16v11H9l-5 4z" /><path d="M8 10h8M8 13h5" />
          </svg>
          <span>receiptflow에 물어보기</span>
        </button>
      )}
      {open && (
        <section className="lp-guide" role="dialog" aria-label="receiptflow 안내 챗봇">
          <header>
            <div>
              <b>receiptflow 안내</b>
              <span>프로젝트 문서를 바탕으로 답해요</span>
            </div>
            <button onClick={() => setOpen(false)} aria-label="닫기">✕</button>
          </header>
          <div className="lp-guide-list" ref={list}>
            <div className="lp-guide-msg assistant">
              서비스가 어떻게 동작하는지, AI·AWS 구조, 사용법까지 무엇이든 물어보세요.
            </div>
            {lines.length === 0 && (
              <div className="lp-guide-starters">
                {STARTERS.map((s) => <button key={s} onClick={() => send(s)}>{s}</button>)}
              </div>
            )}
            {lines.map((l, i) => (
              <div key={i} className={`lp-guide-msg ${l.role}${l.error ? " error" : ""}`}>
                {l.text ? <Rich text={l.text} />
                  : busy && i === lines.length - 1 ? <span className="lp-guide-dots" aria-label="답변 중"><i /><i /><i /></span> : null}
              </div>
            ))}
          </div>
          <form onSubmit={submit}>
            <input value={text} maxLength={300} placeholder="궁금한 점을 물어보세요" aria-label="질문"
              onChange={(e) => setText(e.target.value)} disabled={busy} />
            <button disabled={busy || !text.trim()}>보내기</button>
          </form>
        </section>
      )}
    </>
  );
}
