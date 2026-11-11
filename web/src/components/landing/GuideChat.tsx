import { useEffect, useRef, useState, type FormEvent } from "react";

/**
 * "receiptflow에 물어보기": a chat panel docked on the left, opened from the star in the dark top bar of the
 * intro page and of the app (`Shell`). It answers questions about the service
 * from the project documents (`POST /guide/ask`, its own pod — not the employees' AI assistant).
 * No login. The server limits questions per visitor and per day and says so in the error message.
 */

interface Source { file: string; title: string }
interface Line { role: "user" | "assistant"; text: string; sources?: Source[]; error?: boolean } // sources: kept, not shown

/** Suggested questions: only the core of the build (structure, AWS, AI). Anything else can be typed. */
const STARTERS: { topic: string; questions: string[] }[] = [
  {
    topic: "구조",
    questions: [
      "전체 아키텍처를 설명해 주세요",
      "전체 API를 알려 주세요",
      "DynamoDB 데이터 구조를 알려 주세요",
    ],
  },
  {
    topic: "AWS",
    questions: [
      "어떤 AWS 서비스를 어떻게 썼나요?",
      "EKS 구성과 자동 확장을 설명해 주세요",
      "왜 Lambda가 아니라 EKS인가요?",
    ],
  },
  {
    topic: "AI",
    questions: [
      "Bedrock 모델을 어떻게 나눠 쓰나요?",
      "AI가 틀리지 않게 어떻게 통제하나요?",
      "정확도와 평가 방법을 알려 주세요",
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

/**
 * The chat's button in the dark top bar, like the console's AI sparkle: a large star with a sharp
 * star-shaped hole and a small solid one: white while closed, blue on hover, purple while the chat is open. Pressing it again closes it.
 */
export function GuideStar({ open, onClick }: { open: boolean; onClick: () => void }) {
  return (
    <button className={`lp-guide-star${open ? " on" : ""}`} onClick={onClick} aria-pressed={open}
      aria-label={open ? "AI 챗봇 닫기" : "AI 챗봇 열기"} title="receiptflow에 물어보기">
      <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden>
        {/* traced from the console's AI icon: big star with a star-shaped hole, small solid star */}
        <path fill="currentColor" fillRule="evenodd" d="M2.03 12.69L2.12 12.24L2.35 11.81L2.88 11.44L3.54 11.14L4.23 10.89L4.77 10.66L5.28 10.46L5.74 10.28L6.12 10.11L6.49 9.96L6.86 9.83L7.18 9.71L7.47 9.58L7.73 9.46L8.01 9.37L8.27 9.27L8.5 9.17L8.68 9.03L8.83 8.85L8.93 8.62L9.02 8.36L9.12 8.08L9.24 7.81L9.36 7.53L9.49 7.21L9.62 6.84L9.77 6.47L9.94 6.09L10.12 5.63L10.31 5.11L10.54 4.58L10.79 3.89L11.1 3.22L11.47 2.69L11.9 2.47L12.34 2.38L12.79 2.47L13.22 2.69L13.59 3.22L13.9 3.89L14.14 4.58L14.37 5.11L14.57 5.63L14.75 6.09L14.92 6.47L15.07 6.84L15.2 7.21L15.32 7.53L15.45 7.81L15.57 8.08L15.67 8.36L15.76 8.62L15.86 8.85L16 9.03L16.18 9.17L16.41 9.27L16.67 9.37L16.95 9.46L17.22 9.58L17.5 9.71L17.82 9.83L18.19 9.96L18.56 10.11L18.95 10.28L19.41 10.46L19.92 10.66L20.46 10.89L21.15 11.14L21.81 11.44L22.34 11.81L22.56 12.24L22.66 12.69L22.56 13.13L22.34 13.56L21.81 13.93L21.15 14.24L20.46 14.49L19.92 14.72L19.41 14.91L18.95 15.09L18.56 15.26L18.19 15.42L17.82 15.54L17.5 15.67L17.22 15.79L16.95 15.92L16.67 16.01L16.41 16.1L16.18 16.2L16 16.35L15.86 16.53L15.76 16.76L15.67 17.02L15.57 17.3L15.45 17.56L15.32 17.85L15.2 18.17L15.07 18.54L14.92 18.91L14.75 19.29L14.57 19.75L14.37 20.26L14.14 20.8L13.9 21.49L13.59 22.15L13.22 22.68L12.79 22.91L12.34 23L11.9 22.91L11.47 22.68L11.1 22.15L10.79 21.49L10.54 20.8L10.31 20.26L10.12 19.75L9.94 19.29L9.77 18.91L9.62 18.54L9.49 18.17L9.36 17.85L9.24 17.56L9.12 17.3L9.02 17.02L8.93 16.76L8.83 16.53L8.68 16.35L8.5 16.2L8.27 16.1L8.01 16.01L7.73 15.92L7.47 15.79L7.18 15.67L6.86 15.54L6.49 15.42L6.12 15.26L5.74 15.09L5.28 14.91L4.77 14.72L4.23 14.49L3.54 14.24L2.88 13.93L2.35 13.56L2.12 13.13ZM7.38 12.69L7.56 12.48L7.96 12.3L8.32 12.16L8.67 12.04L8.93 11.93L9.16 11.83L9.35 11.74L9.54 11.67L9.71 11.6L9.89 11.54L10.04 11.49L10.17 11.43L10.29 11.38L10.4 11.32L10.5 11.27L10.58 11.21L10.66 11.15L10.74 11.08L10.8 11.01L10.86 10.92L10.93 10.84L10.98 10.74L11.04 10.64L11.09 10.52L11.15 10.39L11.2 10.23L11.25 10.06L11.32 9.89L11.4 9.7L11.49 9.5L11.59 9.28L11.7 9.01L11.81 8.66L11.96 8.3L12.13 7.91L12.34 7.73L12.55 7.91L12.73 8.3L12.87 8.66L12.99 9.01L13.1 9.28L13.2 9.5L13.29 9.7L13.36 9.89L13.43 10.06L13.49 10.23L13.54 10.39L13.6 10.52L13.65 10.64L13.71 10.74L13.76 10.84L13.82 10.92L13.88 11.01L13.95 11.08L14.03 11.15L14.11 11.21L14.19 11.27L14.29 11.32L14.39 11.38L14.51 11.43L14.64 11.49L14.8 11.54L14.97 11.6L15.14 11.67L15.34 11.74L15.53 11.83L15.75 11.93L16.02 12.04L16.37 12.16L16.73 12.3L17.12 12.48L17.3 12.69L17.12 12.9L16.73 13.07L16.37 13.22L16.02 13.34L15.75 13.44L15.53 13.54L15.34 13.63L15.14 13.71L14.97 13.78L14.8 13.83L14.64 13.88L14.51 13.94L14.39 13.99L14.29 14.05L14.19 14.1L14.11 14.17L14.03 14.23L13.95 14.3L13.88 14.37L13.82 14.45L13.76 14.53L13.71 14.63L13.65 14.74L13.6 14.86L13.54 14.99L13.49 15.14L13.43 15.32L13.36 15.49L13.29 15.68L13.2 15.87L13.1 16.1L12.99 16.36L12.87 16.71L12.73 17.07L12.55 17.47L12.34 17.65L12.13 17.47L11.96 17.07L11.81 16.71L11.7 16.36L11.59 16.1L11.49 15.87L11.4 15.68L11.32 15.49L11.25 15.32L11.2 15.14L11.15 14.99L11.09 14.86L11.04 14.74L10.98 14.63L10.93 14.53L10.86 14.45L10.8 14.37L10.74 14.3L10.66 14.23L10.58 14.17L10.5 14.1L10.4 14.05L10.29 13.99L10.17 13.94L10.04 13.88L9.89 13.83L9.71 13.78L9.54 13.71L9.35 13.63L9.16 13.54L8.93 13.44L8.67 13.34L8.32 13.22L7.96 13.07L7.56 12.9Z" />
        <path fill="currentColor" d="M1.34 4.37L1.44 4.23L1.65 4.1L1.9 4L2.16 3.92L2.35 3.85L2.53 3.78L2.65 3.72L2.79 3.67L2.89 3.62L2.99 3.57L3.07 3.51L3.16 3.47L3.27 3.45L3.36 3.42L3.43 3.39L3.5 3.35L3.56 3.31L3.61 3.26L3.66 3.22L3.7 3.16L3.73 3.09L3.76 3.01L3.79 2.92L3.82 2.82L3.86 2.72L3.91 2.65L3.96 2.55L4.02 2.45L4.06 2.31L4.13 2.18L4.19 2.01L4.26 1.81L4.35 1.56L4.45 1.31L4.57 1.09L4.72 1L4.86 1.09L4.98 1.31L5.09 1.56L5.17 1.81L5.24 2.01L5.3 2.18L5.37 2.31L5.42 2.45L5.47 2.55L5.52 2.65L5.57 2.72L5.61 2.82L5.64 2.92L5.67 3.01L5.7 3.09L5.74 3.16L5.77 3.22L5.82 3.26L5.87 3.31L5.93 3.35L6 3.39L6.07 3.42L6.16 3.45L6.27 3.47L6.36 3.51L6.44 3.57L6.54 3.62L6.64 3.67L6.78 3.72L6.9 3.78L7.08 3.85L7.27 3.92L7.53 4L7.78 4.1L8 4.23L8.09 4.37L8 4.51L7.78 4.64L7.53 4.74L7.27 4.82L7.08 4.9L6.9 4.96L6.78 5.02L6.64 5.07L6.54 5.13L6.44 5.18L6.36 5.23L6.27 5.27L6.16 5.29L6.07 5.32L6 5.36L5.93 5.39L5.87 5.43L5.82 5.48L5.77 5.53L5.74 5.59L5.7 5.66L5.67 5.73L5.64 5.82L5.61 5.92L5.57 6.02L5.52 6.1L5.47 6.2L5.42 6.29L5.37 6.44L5.3 6.56L5.24 6.73L5.17 6.93L5.09 7.18L4.98 7.44L4.86 7.65L4.72 7.74L4.57 7.65L4.45 7.44L4.35 7.18L4.26 6.93L4.19 6.73L4.13 6.56L4.06 6.44L4.02 6.29L3.96 6.2L3.91 6.1L3.86 6.02L3.82 5.92L3.79 5.82L3.76 5.73L3.73 5.66L3.7 5.59L3.66 5.53L3.61 5.48L3.56 5.43L3.5 5.39L3.43 5.36L3.36 5.32L3.27 5.29L3.16 5.27L3.07 5.23L2.99 5.18L2.89 5.13L2.79 5.07L2.65 5.02L2.53 4.96L2.35 4.9L2.16 4.82L1.9 4.74L1.65 4.64L1.44 4.51Z" />
      </svg>
    </button>
  );
}

/** The chat panel; `open` and the star that toggles it live in the page (`Landing`). */
export default function GuideChat({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [lines, setLines] = useState<Line[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggest, setSuggest] = useState(true); // the suggested-questions tray; reopened any time
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    list.current?.scrollTo({ top: lines.length ? list.current.scrollHeight : 0 }); // the welcome stays at the top
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
      {open && (
        <section className="lp-guide" role="dialog" aria-label="receiptflow AI 챗봇">
          <header>
            <b>receiptflow AI 챗봇</b>
            <button disabled={busy || lines.length === 0} onClick={() => { setLines([]); setSuggest(true); }} aria-label="새 대화" title="새 대화">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M12 5v14M5 12h14" /></svg>
            </button>
            <button onClick={onClose} aria-label="닫기" title="닫기">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M15 5l-7 7 7 7" /></svg>
            </button>
          </header>
          <div className="lp-guide-list" ref={list}>
            {lines.length === 0 && (
              <div className="lp-guide-hello">
                <svg width="72" height="72" viewBox="0 0 72 72" aria-hidden>
                  <defs><linearGradient id="lp-guide-hex" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#5b7cf2" /><stop offset="1" stopColor="#a36cf0" /></linearGradient></defs>
                  <path d="M36 4l27 15.500v33L36 68 9 52.500v-33z" fill="url(#lp-guide-hex)" />
                  <path d="M33 20c1.100 8 4.900 11.800 13 13-8.100 1.200-11.900 5-13 13-1.100-8-4.900-11.800-13-13 8.100-1.200 11.900-5 13-13z" fill="#fff" />
                  <path d="M47 39c.5 3.400 1.600 4.500 5 5-3.400.5-4.500 1.600-5 5-.5-3.400-1.600-4.500-5-5 3.400-.5 4.500-1.600 5-5z" fill="#fff" />
                </svg>
                <b>안녕하세요, receiptflow AI 챗봇이에요</b>
                <p>이 프로젝트에 대해 궁금한 것은 무엇이든 편하게 물어보세요. 어디서부터 물어볼지 고민되면 아래 추천 질문을 눌러 보세요.</p>
              </div>
            )}
            {lines.map((l, i) => (
              <div key={i} className={`lp-guide-msg ${l.role}${l.error ? " error" : ""}`}>
                {l.text ? (l.role === "assistant" && !l.error ? <Markdown text={l.text} /> : l.text)
                  : busy && i === lines.length - 1 ? <span className="lp-guide-dots" aria-label="답변 중"><i /><i /><i /></span> : null}
              </div>
            ))}
          </div>
          {suggest && (
            <div className="lp-guide-tray" aria-label="추천 질문">
              {STARTERS.map((g) => (
                <div key={g.topic}>
                  <b>{g.topic}</b>
                  <div className="lp-guide-starters">
                    {g.questions.map((q) => <button key={q} disabled={busy} onClick={() => send(q)}>{q}</button>)}
                  </div>
                </div>
              ))}
            </div>
          )}
          <button type="button" className="lp-guide-toggle" aria-expanded={suggest} onClick={() => setSuggest((v) => !v)}>
            {suggest ? "추천 질문 닫기 ▾" : "추천 질문 보기 ▴"}
          </button>
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
