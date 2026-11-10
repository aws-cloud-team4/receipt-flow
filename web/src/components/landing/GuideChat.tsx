import { useEffect, useRef, useState, type FormEvent } from "react";

/**
 * "receiptflow에 물어보기": a floating chat on the intro page that answers questions about the service
 * from the project documents (`POST /guide/ask`, its own pod — not the employees' AI assistant).
 * No login. The server limits questions per visitor and per day and says so in the error message.
 */

interface Source { file: string; title: string }
interface Line { role: "user" | "assistant"; text: string; sources?: Source[]; error?: boolean } // sources: kept, not shown

/** Suggested questions by technical topic: what developers and demo-day judges ask about the build. */
const STARTERS: { topic: string; questions: string[] }[] = [
  {
    topic: "아키텍처",
    questions: [
      "전체 아키텍처를 설명해 주세요",
      "영수증 한 장이 지나가는 흐름을 단계별로 알려 주세요",
      "서비스 4개는 각각 무슨 일을 하나요?",
      "서비스끼리는 어떻게 연결되나요?",
      "왜 이 기술들을 선택했나요?",
      "저장소 폴더 구조를 알려 주세요",
    ],
  },
  {
    topic: "API",
    questions: [
      "전체 API를 알려 주세요",
      "증빙 API와 오류 코드를 알려 주세요",
      "검수 API와 검토 포인트를 알려 주세요",
      "관리자 API를 알려 주세요",
      "챗봇 API의 SSE 이벤트 형식은 어떻게 되나요?",
      "사진 보정 API(detect·apply)는 어떻게 동작하나요?",
    ],
  },
  {
    topic: "데이터 구조",
    questions: [
      "DynamoDB 테이블 구조를 상세히 알려 주세요",
      "증빙의 상태는 어떻게 바뀌나요?",
      "증빙 칸(필드) 목록과 규칙을 알려 주세요",
      "자동 점검과 점검 사유는 어떻게 동작하나요?",
      "S3와 SQS는 어떻게 구성돼 있나요?",
    ],
  },
  {
    topic: "AWS·배포",
    questions: [
      "어떤 AWS 서비스를 어떻게 썼나요?",
      "Terraform 스택 6개는 각각 무엇을 만드나요?",
      "EKS 구성과 자동 확장을 설명해 주세요",
      "CI/CD와 자동 배포는 어떻게 되나요?",
      "서비스별 IAM 권한은 어떻게 나눴나요?",
      "왜 Lambda가 아니라 EKS인가요?",
      "AWS 비용은 어떻게 관리하나요?",
    ],
  },
  {
    topic: "AI",
    questions: [
      "Bedrock 모델을 어떻게 나눠 쓰나요?",
      "영수증 추출은 어떻게 동작하나요?",
      "AI 어시스턴트의 도구 7개를 알려 주세요",
      "모델을 부르지 않는 턴은 무엇인가요?",
      "서버가 AI 답을 검사하는 규칙은 무엇인가요?",
      "영수증 테두리는 어떻게 찾나요?",
      "정확도와 평가 방법을 알려 주세요",
    ],
  },
  {
    topic: "인증·보안",
    questions: [
      "로그인과 토큰 검증은 어떻게 하나요?",
      "역할별 권한은 어떻게 나뉘나요?",
      "개인정보와 카드번호는 어떻게 다루나요?",
      "개발자 모드는 어떻게 동작하나요?",
    ],
  },
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

/** Inline marks the guide uses: **bold** and `code`; everything else stays text (no HTML is parsed). */
function Inline({ text }: { text: string }) {
  return <>{text.split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? <b key={i}>{part.slice(2, -2)}</b>
      : part.length > 2 && part.startsWith("`") && part.endsWith("`") ? <code key={i}>{part.slice(1, -1)}</code>
      : part)}</>;
}

const cells = (row: string) =>
  row.trim().replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));

/**
 * The small Markdown subset the guide answers in: headings, tables, bullet and numbered lists,
 * paragraphs. Rendered as React elements (never as HTML), so model text cannot inject markup.
 */
function Markdown({ text }: { text: string }) {
  const lines = text.replace(/\r/g, "").split("\n");
  const blocks: JSX.Element[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (line.trim().startsWith("```")) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) code.push(lines[i++]);
      i++; // closing fence (or the end while the answer is still streaming)
      blocks.push(<pre key={i} className="md-code">{code.join("\n")}</pre>);
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push(<p key={i} className="md-h"><Inline text={heading[2]} /></p>);
      i++;
      continue;
    }
    if (line.trim().startsWith("|")) {
      const rows: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(lines[i++]);
      const body = rows.filter((r) => !/^\s*\|?\s*:?-{2,}/.test(r));
      const [head, ...rest] = body.map(cells);
      blocks.push(
        <div key={i} className="md-table"><table>
          {head && <thead><tr>{head.map((c, j) => <th key={j}><Inline text={c} /></th>)}</tr></thead>}
          <tbody>{rest.map((r, k) => <tr key={k}>{r.map((c, j) => <td key={j}><Inline text={c} /></td>)}</tr>)}</tbody>
        </table></div>,
      );
      continue;
    }
    const bullet = /^\s*[-*]\s+/;
    const numbered = /^\s*\d+[.)]\s+/;
    if (bullet.test(line) || numbered.test(line)) {
      const ordered = numbered.test(line);
      const pattern = ordered ? numbered : bullet;
      const items: string[] = [];
      while (i < lines.length && (pattern.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        if (pattern.test(lines[i])) items.push(lines[i].replace(pattern, ""));
        else items[items.length - 1] += " " + lines[i].trim();
        i++;
      }
      const List = ordered ? "ol" : "ul";
      blocks.push(<List key={i}>{items.map((t, k) => <li key={k}><Inline text={t} /></li>)}</List>);
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,4}\s|\s*\||\s*[-*]\s|\s*\d+[.)]\s|\s*```)/.test(lines[i])) para.push(lines[i++]);
    blocks.push(<p key={i}><Inline text={para.join("\n")} /></p>);
  }
  return <div className="md">{blocks}</div>;
}

/** A friendly robot head: antenna, ears, two eyes and a smile (the open button and the panel header). */
function BotIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <path d="M16 3.5v4" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
      <circle cx="16" cy="3.2" r="2" fill="#ffd166" />
      <rect x="2" y="14" width="3.5" height="7" rx="1.5" fill="#fff" opacity=".75" />
      <rect x="26.5" y="14" width="3.5" height="7" rx="1.5" fill="#fff" opacity=".75" />
      <rect x="5.5" y="7.5" width="21" height="19" rx="6.5" fill="#fff" />
      <circle cx="12" cy="15.5" r="2.3" fill="#3b56c9" />
      <circle cx="20" cy="15.5" r="2.3" fill="#3b56c9" />
      <path d="M12 20.8c1.2 1.3 2.5 1.9 4 1.9s2.8-.6 4-1.9" stroke="#3b56c9" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

export default function GuideChat() {
  const [open, setOpen] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggest, setSuggest] = useState(true); // suggested questions; can be reopened mid-chat
  const [topic, setTopic] = useState(0);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight });
  }, [lines, open]);

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    const history = lines;
    setText("");
    setSuggest(false);
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
        <button className="lp-guide-fab" onClick={() => setOpen(true)} aria-label="AI 안내 챗봇 열기" title="receiptflow에 물어보기">
          <BotIcon size={34} />
        </button>
      )}
      {open && (
        <section className="lp-guide" role="dialog" aria-label="receiptflow 안내 챗봇">
          <header className="lp-guide-head">
            <span className="lp-guide-mark" aria-hidden>
              <BotIcon size={24} />
            </span>
            <div className="lp-guide-title">
              <b>receiptflow 안내</b>
              <span>아키텍처·API·AWS·AI, 프로젝트 문서로 답해요</span>
            </div>
            <button disabled={busy || lines.length === 0} onClick={() => { setLines([]); setSuggest(true); }}>새 대화</button>
            <button className="lp-guide-close" onClick={() => setOpen(false)} aria-label="닫기">✕</button>
          </header>

          <div className="lp-guide-list" ref={list}>
            {lines.length === 0 && (
              <div className="lp-guide-hello">
                <b>무엇이든 물어보세요</b>
                전체 구조부터 API 한 줄까지, 아래 추천 질문을 누르거나 직접 입력해 주세요.
              </div>
            )}
            {lines.map((l, i) => (
              <div key={i} className={`lp-guide-msg ${l.role}${l.error ? " error" : ""}`}>
                {l.text ? (l.role === "assistant" && !l.error ? <Markdown text={l.text} /> : l.text)
                  : busy && i === lines.length - 1 ? <span className="lp-guide-dots" aria-label="답변 중"><i /><i /><i /></span> : null}
              </div>
            ))}
          </div>

          <div className="lp-guide-suggest">
            <button type="button" className="lp-guide-suggest-bar" aria-expanded={suggest} onClick={() => setSuggest((v) => !v)}>
              <span>추천 질문</span>
              <span>{suggest ? "접기 ▾" : "보기 ▴"}</span>
            </button>
            {suggest && (
              <>
                <div className="lp-guide-tabs" role="tablist" aria-label="추천 질문 주제">
                  {STARTERS.map((g, i) => (
                    <button key={g.topic} type="button" role="tab" aria-selected={i === topic} onClick={() => setTopic(i)}>{g.topic}</button>
                  ))}
                </div>
                <div className="lp-guide-questions">
                  {STARTERS[topic].questions.map((q) => (
                    <button key={q} type="button" disabled={busy} onClick={() => send(q)}>{q}</button>
                  ))}
                </div>
              </>
            )}
          </div>

          <form className="lp-guide-form" onSubmit={submit}>
            <input value={text} maxLength={300} placeholder="궁금한 점을 물어보세요" aria-label="질문"
              onChange={(e) => setText(e.target.value)} disabled={busy} />
            <button disabled={busy || !text.trim()} aria-label="보내기">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                <path d="M12 19V5M6 11l6-6 6 6" />
              </svg>
            </button>
          </form>
        </section>
      )}
    </>
  );
}
