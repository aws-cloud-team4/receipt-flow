import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

/** Console-style help: small "정보" links open a side panel (a bottom sheet on phones) that stays open
 * while you move around, until closed. Texts follow the server rules (domain.py run_checks, review_points). */
export type HelpTopic = "categories" | "amounts" | "checks" | "review_points" | "status" | "photo";

const TITLES: Record<HelpTopic, string> = {
  categories: "지출 분류 기준",
  amounts: "금액과 검산",
  checks: "점검 경고",
  review_points: "검토 포인트",
  status: "증빙 상태",
  photo: "영수증 잘 찍는 법",
};

function Categories() {
  const [items, setItems] = useState<{ code: string; label: string; hint: string }[] | null>(null);
  useEffect(() => {
    api.meta().then((m) => setItems(m.categories), () => setItems([]));
  }, []);
  if (!items) return <p className="muted small">불러오는 중…</p>;
  return (
    <>
      <p>회사가 정한 10가지 중 하나를 골라요. 애매하면 AI 어시스턴트가 영수증 품목과 시간대를 보고 추천해 줘요.</p>
      <dl className="help-dl">
        {items.map((c) => (
          <div key={c.code}>
            <dt>{c.label}</dt>
            <dd>{c.hint}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

const BODIES: Record<HelpTopic, () => ReactNode> = {
  categories: () => <Categories />,
  amounts: () => (
    <>
      <p><b>공급가액 + 부가세 + 면세금액 = 총액</b>이 맞아야 제출할 수 있어요. 맞지 않으면 "오류"로 표시돼요.</p>
      <ul>
        <li><b>면세금액</b>은 마트·우체국·서점처럼 면세 품목이 섞인 영수증에만 찍혀요. 없으면 비워 두세요.</li>
        <li>공급가액·부가세가 영수증에 없으면 비워 둬도 돼요. 그때는 검산하지 않아요.</li>
        <li>AI가 흐리게 읽은 칸은 "확인 필요"로 표시돼요. 사진과 비교해 고쳐 주세요.</li>
      </ul>
    </>
  ),
  checks: () => (
    <>
      <p>제출 전에 서버가 자동으로 점검해요. <b>오류</b>는 고쳐야 제출할 수 있고, <b>확인</b>은 그대로 제출해도 돼요.</p>
      <dl className="help-dl">
        <div><dt>금액 검산 (오류)</dt><dd>공급가액 + 부가세 + 면세 ≠ 총액. 읽힌 금액을 사진과 비교해 고쳐 주세요.</dd></div>
        <div><dt>거래 일시 형식 (오류)</dt><dd>날짜를 알아볼 수 없어요. 예: 2026-10-14 12:41</dd></div>
        <div><dt>심야 (확인)</dt><dd>22시~06시 거래예요. 업무 지출이면 지출 목적에 사유를 적어 주세요.</dd></div>
        <div><dt>주말 (확인)</dt><dd>토·일 거래예요. 업무 지출이면 사유를 적어 주세요.</dd></div>
        <div><dt>중복 (확인)</dt><dd>같은 상호·날짜·금액의 증빙이 이미 있어요. 두 번 올린 건 아닌지 확인하세요.</dd></div>
        <div><dt>같은 승인번호 (확인)</dt><dd>같은 카드 승인번호의 증빙이 이미 있어요. 중복 제출인지 확인하세요.</dd></div>
      </dl>
    </>
  ),
  review_points: () => (
    <>
      <p>승인 전에 먼저 볼 것을 서버가 규칙으로 뽑아요. 색 띠는 <b>빨강 = 오류</b>, <b>노랑 = 주의</b>예요.</p>
      <dl className="help-dl">
        <div><dt>점검 경고</dt><dd>직원 화면과 같은 검산·심야·주말·중복·같은 승인번호 경고예요.</dd></div>
        <div><dt>흐리게 읽힌 칸</dt><dd>AI가 확신하지 못한 칸이에요. 사진과 비교하세요.</dd></div>
        <div><dt>직원이 직접 입력·수정한 칸</dt><dd>AI가 읽은 뒤 사람이 바꾼 칸이에요. 금액이면 주의로 표시돼요.</dd></div>
        <div><dt>AI가 읽지 못함</dt><dd>분석에 실패해 직원이 모두 직접 입력했어요.</dd></div>
        <div><dt>결과 확인을 건너뜀</dt><dd>직원이 AI가 읽은 결과를 확인하지 않고 제출했어요.</dd></div>
        <div><dt>접대·선물비</dt><dd>지출 목적에 상대 거래처가 적혀 있는지 보세요.</dd></div>
        <div><dt>기타 업무비 · 짧은 목적</dt><dd>목적이 구체적인지 보세요.</dd></div>
      </dl>
      <p className="muted small">판단이 어려우면 [건너뛰기]를 누르면 검토 순서의 맨 뒤로 가요.</p>
    </>
  ),
  status: () => (
    <>
      <p className="help-flow">작성 중 → 검토 중 → 승인<br />　　　　　　↘ 보완 요청 → (고쳐서) 검토 중</p>
      <dl className="help-dl">
        <div><dt>작성 중</dt><dd>아직 제출 전이에요. 이때만 삭제할 수 있어요.</dd></div>
        <div><dt>검토 중</dt><dd>제출했고 담당자 확인을 기다려요. 먼저 제출된 순서로 봐요.</dd></div>
        <div><dt>보완 요청</dt><dd>담당자가 사유와 고칠 칸을 적어 돌려보냈어요. 고친 뒤 다시 제출해요.</dd></div>
        <div><dt>승인</dt><dd>끝났어요. 월별 CSV로 회계 정산에 넘어가요.</dd></div>
      </dl>
    </>
  ),
  photo: () => (
    <>
      <ul>
        <li>영수증을 <b>평평하게</b> 펴고, 테두리 네 모서리가 <b>다 보이게</b> 찍어요.</li>
        <li><b>밝은 곳</b>에서, 그림자와 빛 반사를 피해요.</li>
        <li>글자가 흐리면 경고가 떠요. 다시 찍는 게 고치는 것보다 빨라요.</li>
        <li>올린 뒤 서버가 테두리를 찾아요. 모서리를 끌어 맞추면 그 모양대로 반듯하게 잘라요.</li>
        <li>원본 사진도 보관돼서 담당자가 "원본"으로 볼 수 있어요.</li>
      </ul>
      <p className="muted small">카드 결제 영수증만 받아요 (현금·계좌이체·취소 영수증 제외).</p>
    </>
  ),
};

const HelpContext = createContext<{ open: (t: HelpTopic) => void }>({ open: () => {} });

export function HelpProvider({ children }: { children: ReactNode }) {
  const [topic, setTopic] = useState<HelpTopic | null>(null);

  useEffect(() => {
    if (!topic) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setTopic(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [topic]);

  return (
    <HelpContext.Provider value={{ open: setTopic }}>
      {children}
      {topic && (
        <aside className="help-panel" role="complementary" aria-label={`도움말: ${TITLES[topic]}`}>
          <div className="help-head">
            <h2>{TITLES[topic]}</h2>
            <button className="help-close" onClick={() => setTopic(null)} aria-label="도움말 닫기">✕</button>
          </div>
          <div className="help-body">{BODIES[topic]()}</div>
          <div className="help-foot">
            <Link to="/about" onClick={() => setTopic(null)}>서비스 소개 보기 →</Link>
          </div>
        </aside>
      )}
    </HelpContext.Provider>
  );
}

/** Opens a help topic in the side panel. */
export const useHelp = () => useContext(HelpContext);

/** The small blue "정보" link next to a title. */
export function InfoLink({ topic }: { topic: HelpTopic }) {
  const { open } = useContext(HelpContext);
  return (
    <button type="button" className="info-link" onClick={(e) => { e.preventDefault(); e.stopPropagation(); open(topic); }}>
      정보
    </button>
  );
}
