import { useEffect, useState } from "react";
import { useReducedMotion } from "./motion";

// "사용 방법": four steps on the left, a phone on the right that acts each one out.
// Advances by itself every few seconds (paused while hovered, off under reduced motion);
// clicking a step jumps to it. The receipt is the synthetic sample (scripts/make_sample_receipt.py).

export const STEPS = [
  { title: "찍어서 올리기", body: "휴대폰 카메라로 찍으면 서버가 테두리를 찾아 반듯하게 잘라요." },
  { title: "AI 분석", body: "몇 초 안에 영수증의 모든 칸을 읽고, 흐린 칸은 확인 필요로 표시해요." },
  { title: "대화로 완성", body: "결과 확인 → 목적·분류 추천 → 최종 확인 카드에서 직접 제출해요." },
  { title: "검토·승인", body: "담당자는 검토 포인트만 보고 승인하거나, 고칠 칸을 짚어 보완을 요청해요." },
];
const STEP_MS = 4200;

function Receipt({ scanning }: { scanning?: boolean }) {
  return (
    <div className={`demo-receipt${scanning ? " scanning" : ""}`}>
      <b>한빛 김밥천국 역삼점</b>
      <span>2026-10-14 12:41</span>
      <hr />
      <span className="row"><i>참치김밥 x2</i><i>9,000</i></span>
      <span className="row"><i>라볶이 x1</i><i>7,500</i></span>
      <span className="row"><i>돈까스 x2</i><i>19,000</i></span>
      <hr />
      <span className="row total"><i>합계</i><i>35,500</i></span>
      {scanning && <span className="demo-scan" />}
    </div>
  );
}

function Stage({ n }: { n: number }) {
  if (n === 0) {
    return (
      <div className="demo-stage">
        <div className="demo-photo">
          <Receipt />
          {["tl", "tr", "br", "bl"].map((c, i) => <span key={c} className={`demo-corner ${c}`} style={{ animationDelay: `${0.2 + i * 0.15}s` }} />)}
        </div>
        <div className="demo-cta">테두리 확인 · 올리기</div>
      </div>
    );
  }
  if (n === 1) {
    const fields = [["상호", "한빛 김밥천국 역삼점"], ["거래 일시", "2026-10-14 12:41"], ["공급가액", "32,273원"], ["부가세", "3,227원"], ["총액", "35,500원"]];
    return (
      <div className="demo-stage">
        <div className="demo-mini"><Receipt scanning /></div>
        <div className="demo-fields">
          {fields.map(([k, v], i) => (
            <div key={k} className="demo-field" style={{ animationDelay: `${0.5 + i * 0.35}s` }}><span>{k}</span><b>{v}</b></div>
          ))}
          <div className="demo-ok" style={{ animationDelay: "2.4s" }}>✓ 검산 일치 · 공급가액 + 부가세 = 총액</div>
        </div>
      </div>
    );
  }
  if (n === 2) {
    return (
      <div className="demo-stage demo-chat">
        <div className="bubble ai" style={{ animationDelay: "0.1s" }}>영수증을 읽었어요. 내용이 맞는지 확인해 주세요.</div>
        <div className="bubble me" style={{ animationDelay: "0.8s" }}>맞아요</div>
        <div className="bubble ai" style={{ animationDelay: "1.4s" }}>어떤 일로 쓰신 비용인가요?</div>
        <div className="demo-chips" style={{ animationDelay: "2s" }}>
          <span className="picked">팀 점심 식사 · 식사·간식비</span>
          <span>고객 미팅 · 접대·선물비</span>
        </div>
        <div className="demo-submit" style={{ animationDelay: "2.8s" }}>제출하기</div>
      </div>
    );
  }
  return (
    <div className="demo-stage">
      <div className="demo-review">
        <div className="demo-review-head"><b>한빛 김밥천국 역삼점</b><span>35,500원</span></div>
        <div className="demo-point">참고 · 특별히 볼 점이 없어요</div>
        <div className="demo-kv"><span>분류</span><b>식사·간식비</b></div>
        <div className="demo-kv"><span>목적</span><b>팀 점심 식사</b></div>
        <div className="demo-stamp">승인</div>
      </div>
      <div className="demo-next">다음 건으로 →</div>
    </div>
  );
}

export default function StepDemo() {
  const reduced = useReducedMotion();
  const [step, setStep] = useState(0);
  const [paused, setPaused] = useState(false);
  const auto = !reduced && !paused;

  useEffect(() => {
    if (!auto) return;
    const t = setTimeout(() => setStep((s) => (s + 1) % STEPS.length), STEP_MS);
    return () => clearTimeout(t);
  }, [step, auto]);

  return (
    <div className="demo" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}>
      <ol className="demo-steps">
        {STEPS.map((s, i) => (
          <li key={s.title}>
            <button type="button" className={i === step ? "on" : ""} onClick={() => setStep(i)} aria-current={i === step}>
              <span className="demo-n">{String(i + 1).padStart(2, "0")}</span>
              <span className="demo-txt"><b>{s.title}</b><span>{s.body}</span></span>
              <span className="demo-bar">
                <span key={`${step}-${auto}`} className={i === step && auto ? "run" : i === step ? "full" : ""}
                  style={{ animationDuration: `${STEP_MS}ms` }} />
              </span>
            </button>
          </li>
        ))}
      </ol>
      <div className="demo-phone" aria-live="polite">
        <div className="demo-notch" />
        <div className="demo-screen">
          <div className="demo-top"><span className="brand">receipt<span>flow</span></span><span>{STEPS[step].title}</span></div>
          <Stage key={step} n={step} />
        </div>
      </div>
    </div>
  );
}
