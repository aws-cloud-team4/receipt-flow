import { analysisSeconds } from "../analysisTime";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import {
  api,
  chatTurn,
  type ChatMessage,
  type ChatTurn,
  type ExpenseSuggestion,
  type FieldKey,
  type Receipt,
} from "../api";
import { FIELD_LABELS, txDate, won } from "../labels";
import { SubmitReview } from "./ReceiptParts";

interface Props {
  receipt: Receipt;
  editable: boolean;
  onFieldsChanged: () => void;
  /** "직접 수정" on the result card: open the form at the first field that needs a look. */
  onEditRequest: (field: FieldKey | null) => void;
  /** The assistant says the receipt is ready: the same submit as the bottom button. */
  onSubmit: () => void;
  /** "다시 찍기" asked for by the reviewer. */
  onRetake?: () => void;
}

const ANALYZING = ["waiting", "queued", "processing"];
const CARD_FIELDS: FieldKey[] = [
  "merchant_name",
  "transaction_at",
  "total_amount",
  "payment_method",
  "approval_number",
];
const YES_NO = ["예", "아니요"];

/** The AI assistant: shows what the AI is doing, the extraction result, and the conversation (SSE). */
export default function ChatPanel({ receipt, editable, onFieldsChanged, onEditRequest, onSubmit, onRetake }: Props) {
  const receiptId = receipt.id;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streaming, setStreaming] = useState<string | null>(null);
  const [choices, setChoices] = useState<string[]>([]);
  const [suggestions, setSuggestions] = useState<ExpenseSuggestion[]>([]);
  const [pendingSlot, setPendingSlot] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  // The result card's buttons show right away (not tied to busy) and go once one is pressed.
  const [cardAnswered, setCardAnswered] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const log = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const started = useRef(false);
  const status = receipt.analysis_status;
  const analysed = status === "done" || status === "failed";
  const prevStatus = useRef(status);

  // Turns run one after another: a click while the assistant is still preparing (for example the
  // suggestions after the result) shows at once and is sent as soon as that turn ends.
  const inflight = useRef<Promise<void>>(Promise.resolve());

  function send(turn: ChatTurn, label?: string) {
    const said = turn.message ?? label;
    const run = inflight.current.then(() => runTurn(turn, said));
    inflight.current = run.catch(() => {});
    return run;
  }

  async function runTurn(turn: ChatTurn, said: string | undefined) {
    setBusy(true);
    setError(null);
    const now = () => new Date().toISOString();
    // Added when the turn really starts, so a click queued behind the opening reads after it.
    if (said) setMessages((m) => [...m, { at: now(), role: "user", text: said }]);
    setChoices([]);
    setSuggestions([]);
    setStreaming("");
    try {
      const done = await chatTurn(
        receiptId,
        turn,
        (piece) => setStreaming((s) => (s ?? "") + piece),
        // A tool ran: what was written before it was a draft, the summary line replaces it.
        (tool) => {
          setStreaming("");
          setMessages((m) => [...m, { at: now(), role: "tool", text: tool.summary }]);
        },
      );
      if (!done.repeat && done.text) {
        setMessages((m) => [
          ...m,
          { at: now(), role: "assistant", text: done.text, slot: done.slot, actions: done.actions ?? [] },
        ]);
      }
      setChoices(done.choices);
      setSuggestions(done.suggestions ?? []);
      setPendingSlot(done.slot);
      if (said || done.changed) onFieldsChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStreaming(null);
      setBusy(false);
    }
  }

  // Load history, then open the conversation (or announce a result that arrived while away).
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    // Part of the turn queue, so a card click made while this loads waits for it (and its first turn).
    const loading = api.chatMessages(receiptId).then(
      ({ items }) => {
        setMessages(items);
        const last = [...items].reverse().find((m) => m.role === "assistant");
        setPendingSlot(last?.slot ?? null);
        if (items.at(-1)?.role === "assistant") {
          // Not answered yet: bring its buttons back.
          setChoices(last?.choices ?? []);
          setSuggestions(last?.suggestions ?? []);
        }
        if (!editable) return;
        const finished = receipt.timings?.analysis_finished;
        // The assistant speaks first once the result is in; a reply written during the analysis
        // would sit under the result card and read like an old message.
        if (analysed && (!last || last.slot === "wait_analysis" || (finished && last.at < finished))) {
          return runTurn({ event: "analysis_done" }, undefined);
        }
        if (receipt.review_status === "changes_requested") {
          return runTurn({ event: "changes_requested" }, undefined); // said once per request (server)
        }
      },
      (e) => setError(e.message),
    );
    inflight.current = loading.catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [receiptId]);

  // Extraction finished while the page is open → the assistant goes over the result.
  useEffect(() => {
    const was = prevStatus.current;
    prevStatus.current = status;
    if (editable && ANALYZING.includes(was) && analysed && started.current) send({ event: "analysis_done" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  // The result card sits in the timeline at the moment the analysis finished.
  const finishedAt = receipt.timings?.analysis_finished;
  const timeline = useMemo(() => {
    type Item = { kind: "msg"; m: ChatMessage } | { kind: "card"; at: string } | { kind: "review"; last: boolean };
    const items: Item[] = [];
    // The final review card sits right after the message that offered it; only the last one is live.
    const reviews = messages.flatMap((m, i) => (m.actions?.includes("submit") ? [i] : []));
    // Live only while it is the latest word from the assistant (a later request or question replaces it).
    const lastAssistant = messages.map((m) => m.role).lastIndexOf("assistant");
    messages.forEach((m, i) => {
      items.push({ kind: "msg", m });
      if (reviews.includes(i)) items.push({ kind: "review", last: i === lastAssistant });
    });
    if (status === "done" && finishedAt) {
      const i = items.findIndex((it) => it.kind === "msg" && it.m.at > finishedAt);
      items.splice(i === -1 ? items.length : i, 0, { kind: "card", at: finishedAt });
    }
    return items;
  }, [messages, status, finishedAt]);

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: "smooth" });
  }, [timeline.length, streaming]);

  function submit(e: FormEvent) {
    e.preventDefault();
    const value = text.trim();
    if (!value || busy) return;
    setText("");
    send({ message: value });
  }

  // The card buttons are said in the conversation, so the assistant knows what the employee decided.
  function confirmCard() {
    setCardAnswered(true);
    send({ message: "맞아요" });
  }

  // Buttons that act on the screen as well as in the conversation.
  function choose(c: string) {
    if (c === "다시 찍기" && onRetake) return onRetake();
    if (c === "직접 수정") {
      const field = (receipt.review_fields ?? []).find((k) => k !== "photo") as FieldKey | undefined;
      onEditRequest(field ?? receipt.needs_check[0] ?? null);
    }
    send({ message: c });
  }

  function editCard() {
    setCardAnswered(true);
    onEditRequest(receipt.needs_check[0] ?? null);
    send({ message: "직접 수정" });
  }

  const took = analysisSeconds(receipt);

  return (
    <section className="panel assistant-panel" aria-label="AI 어시스턴트">
      <div className="assistant-head">
        <span className="assistant-mark" aria-hidden>
          <Sparkle />
        </span>
        <h2>AI 어시스턴트</h2>
        <span className="spacer" />
        {ANALYZING.includes(status) && status !== "waiting" && <span className="assistant-status working">영수증 읽는 중…</span>}
        {status === "done" && <span className="assistant-status ok">분석 완료{took ? ` ${took}초` : ""}</span>}
        {status === "failed" && <span className="assistant-status err">분석 실패</span>}
      </div>

      <AnalysisSteps receipt={receipt} />

      <div className="chat-log" ref={log} aria-live="polite">
        {timeline.map((it, i) =>
          it.kind === "card" ? (
            <ResultCard key="card" receipt={receipt} confirmed={!!receipt.result_confirmed_at}
              editable={editable && !cardAnswered} onConfirm={confirmCard} onEdit={editCard} />
          ) : it.kind === "review" ? (
            it.last && (editable || receipt.review_status !== "draft") ? (
              <SubmitReview key={`review-${i}`} receipt={receipt} busy={busy || ANALYZING.includes(status)}
                submitted={!editable} onSubmit={onSubmit} onEdit={editCard} />
            ) : (
              <div key={`review-${i}`} className="tool-line muted">제출 확인 요청 (이후 고친 내용으로 다시 확인)</div>
            )
          ) : it.m.role === "tool" ? (
            <div key={i} className="tool-line"><Sparkle />{it.m.text}</div>
          ) : (
            <div key={i} className={`bubble ${it.m.role}`}>{it.m.text}</div>
          ),
        )}
        {editable && messages.length === 0 && streaming === null && ANALYZING.includes(status) && (
          // Shown only on screen, not stored: the assistant's real first message comes with the result.
          <div className="bubble assistant">영수증을 읽고 있어요. 끝나면 확인할 내용을 알려 드릴게요.</div>
        )}
        {streaming !== null &&
          (streaming === "" ? (
            <div className="bubble assistant typing" aria-label="AI가 입력 중"><span /><span /><span /></div>
          ) : (
            <div className="bubble assistant">{streaming}</div>
          ))}
        {error && <div className="alert error">{error}</div>}
      </div>

      {editable && suggestions.length > 0 && (
        <div className="choices suggestions" aria-label="AI 추천 지출 목적과 분류">
          {suggestions.map((sg) => (
            <button key={sg.purpose} className="suggested" disabled={busy}
              onClick={() => send({ choice: { purpose: sg.purpose, category: sg.category } },
                `${sg.purpose} · ${sg.category_label}`)}>
              <Sparkle />
              {sg.purpose}
              <span className="choice-tag">{sg.category_label}</span>
            </button>
          ))}
          <button disabled={busy} onClick={() => input.current?.focus()}>직접 입력</button>
        </div>
      )}
      {editable && choices.length > 0 && (
        <div className={`choices${isYesNo(choices) ? " yes-no" : ""}`}>
          {choices.map((c, i) => (
            <button key={c} className={pendingSlot === "category" && i === 0 ? "suggested" : ""} disabled={busy}
              onClick={() => choose(c)}>
              {pendingSlot === "category" && i === 0 && <Sparkle />}
              {c}
            </button>
          ))}
        </div>
      )}
      {editable ? (
        <form className="chat-input" onSubmit={submit}>
          <input ref={input} value={text} onChange={(e) => setText(e.target.value)} placeholder="AI에게 답하거나 물어보세요"
            aria-label="AI 어시스턴트에게 보내기" maxLength={500}
            onFocus={(e) => {
              // Phones: the sticky submit bar and the keyboard can cover the input, so bring it to the middle.
              const el = e.currentTarget;
              if (matchMedia("(max-width: 900px)").matches) setTimeout(() => el.scrollIntoView({ block: "center", behavior: "smooth" }), 300);
            }} />
          <button className="btn btn-blue" disabled={busy || !text.trim()}>보내기</button>
        </form>
      ) : (
        <div className="chat-input muted small">제출된 증빙은 대화로 수정할 수 없어요.</div>
      )}
    </section>
  );
}

/** 사진 받음 → 테두리 보정 → AI가 읽기 → 결과 확인 */
function AnalysisSteps({ receipt }: { receipt: Receipt }) {
  const s = receipt.analysis_status;
  const steps = [
    { label: "사진 받음", done: s !== "waiting" },
    { label: "테두리 보정", done: !!receipt.preprocess || s === "done" },
    { label: "AI가 읽기", done: s === "done", active: s === "queued" || s === "processing", failed: s === "failed" },
    { label: "결과 확인", done: false, active: s === "done" },
  ];
  return (
    <ol className="steps" aria-label="분석 단계">
      {steps.map((st) => (
        <li key={st.label} className={st.failed ? "failed" : st.done ? "done" : st.active ? "active" : ""}>
          {st.label}
        </li>
      ))}
    </ol>
  );
}

function ResultCard({ receipt, confirmed, editable, onConfirm, onEdit }: {
  receipt: Receipt;
  confirmed: boolean;
  editable: boolean;
  onConfirm: () => void;
  onEdit: () => void;
}) {
  const f = receipt.fields;
  const unsure = new Set(receipt.needs_check);
  const mismatch = receipt.checks.some((c) => c.code === "amount_mismatch");
  const allAmounts = f.supply_amount != null && f.vat_amount != null && f.total_amount != null;
  // As printed (digits, * and -): a partial number may be the first digits, not the last four.
  const card = [f.card_issuer, f.card_number].filter(Boolean).join(" ");
  const value = (k: FieldKey) =>
    k === "total_amount" ? won(f.total_amount)
      : k === "transaction_at" ? txDate(f.transaction_at)
      : k === "payment_method" ? [f.payment_method, card].filter(Boolean).join(" · ") || "—"
      : (f[k] as string) ?? "—";
  return (
    <div className="result-card">
      <p>{confirmed ? "확인한 결과" : "AI가 읽은 결과"}</p>
      <dl>
        {CARD_FIELDS.map((k) => (
          <div key={k} style={{ display: "contents" }}>
            <dt>{FIELD_LABELS[k]}</dt>
            <dd>
              {value(k)}
              {unsure.has(k) && <span className="tag warn">확인 필요</span>}
              {k === "total_amount" && allAmounts && (
                <span className={`tag ${mismatch ? "err" : "ok"}`}>{mismatch ? "검산 불일치" : "검산 일치"}</span>
              )}
            </dd>
          </div>
        ))}
      </dl>
      {editable && !confirmed && (
        <div className="result-actions">
          <button className="btn btn-ghost" onClick={onConfirm}>맞아요</button>
          <button className="btn btn-ghost" onClick={onEdit}>직접 수정</button>
        </div>
      )}
    </div>
  );
}

function isYesNo(choices: string[]) {
  return choices.length === 2 && choices.every((c) => YES_NO.includes(c));
}

function Sparkle() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
      <path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9z" />
      <path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8z" />
    </svg>
  );
}
