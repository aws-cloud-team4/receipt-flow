import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ChatArt, CheckArt, ScanArt } from "../components/landing/CardArt";
import HeroArt from "../components/landing/HeroArt";
import Architecture from "../components/landing/Architecture";
import { useReveal } from "../components/landing/motion";
import { EmployeeArt, ReviewerArt } from "../components/landing/RoleArt";
import StepDemo from "../components/landing/StepDemo";
import UsageSection from "../components/landing/UsageCard";
import "./landing.css";

// Public intro page for signed-out visitors. The layout follows a cloud-provider marketing home
// (utility bar, white nav with a dark pill, a blue hero with flowing routes and a translucent
// card, a white body curving up over it, art-topped cards); name, copy and art are our own.

const FEATURES: { tag: string; title: string; body: string; art: ReactNode; href: string }[] = [
  {
    tag: "AI 영수증 인식",
    title: "찍기만 하면 칸이 채워져요",
    body: "상호·일시·금액·부가세·면세·승인번호까지. 흐리게 읽힌 칸은 확인 필요로 표시해요.",
    art: <ScanArt />,
    href: "#how",
  },
  {
    tag: "대화형 어시스턴트",
    title: "목적과 분류는 AI와 함께",
    body: "결과를 확인하고, 품목과 시간대를 보고 고른 추천 중 하나만 누르면 돼요. 제출은 언제나 사람이 해요.",
    art: <ChatArt />,
    href: "#how",
  },
  {
    tag: "자동 점검",
    title: "검산·중복은 서버가 먼저",
    body: "공급가액 + 부가세 + 면세 = 총액, 같은 승인번호, 심야·주말 거래를 제출 전에 알려 줘요.",
    art: <CheckArt />,
    href: "#roles",
  },
];

const ROLES = [
  {
    who: "직원",
    kind: "employee",
    art: <EmployeeArt />,
    title: "영수증 한 장, 1분이면 끝",
    points: ["사진 한 장으로 시작", "AI가 칸 채우기·분류 추천", "보완 요청은 사유와 고칠 칸까지 안내", "내 할 일·월별 지출을 한눈에"],
  },
  {
    who: "검수 담당자",
    kind: "reviewer",
    art: <ReviewerArt />,
    title: "볼 것만 먼저 보이게",
    points: ["먼저 제출된 순서의 대기열", "오류·주의를 규칙으로 정리한 검토 포인트", "사진·원본·직원과 AI의 대화를 한 화면에", "애매한 건은 건너뛰기, 월별 CSV"],
  },
];

export default function Landing() {
  const page = useReveal<HTMLDivElement>();

  return (
    <div className="lp" ref={page}>
      <div className="lp-util">
        <div className="lp-wrap lp-util-row">
          <span>AWS 클라우드 AI 부트캠프 4팀</span>
          <a href="#how">도움말</a>
          <Link to="/login">로그인</Link>
        </div>
      </div>

      <header className="lp-nav">
        <div className="lp-wrap lp-nav-row">
          <Link to="/" className="brand lp-brand" aria-label="receiptflow">receipt<span>flow</span></Link>
          <span className="lp-divider" />
          <nav className="lp-links" aria-label="소개">
            <a href="#features">기능</a>
            <a href="#how">사용 방법</a>
            <a href="#roles">직원·담당자</a>
            <a href="#stack">아키텍처</a>
            <a href="#cost">AWS 비용</a>
          </nav>
          <span className="lp-spacer" />
          <Link to="/login" className="lp-signin">로그인</Link>
          <Link to="/login" className="lp-pill">시작하기</Link>
        </div>
      </header>

      <section className="lp-hero">
        <HeroArt />
        <div className="lp-wrap">
          <div className="lp-hero-card">
            <h1>영수증 한 장으로 끝나는<br />경비 처리</h1>
            <p>찍어서 올리면 AI가 읽고, 목적과 분류를 함께 정하고, 담당자는 검토 포인트만 확인해요.</p>
            <Link to="/login" className="lp-pill lp-pill-lg">로그인하고 시작하기</Link>
          </div>
        </div>
      </section>

      <main className="lp-body">
        <section id="features" className="lp-wrap lp-section">
          <h2 className="reveal">이렇게 달라져요</h2>
          <p className="lp-lead reveal">손으로 옮겨 적고, 분류를 고민하고, 금액을 다시 맞춰 보던 일을 줄여요.</p>
          <div className="lp-cards">
            {FEATURES.map((f, i) => (
              <a key={f.tag} href={f.href} className="lp-card reveal" style={{ transitionDelay: `${i * 90}ms` }}>
                <div className="lp-card-art">
                  {f.art}
                  <span className="lp-chip">{f.tag}</span>
                </div>
                <div className="lp-card-body">
                  <h3>{f.title}</h3>
                  <p>{f.body}</p>
                  <span className="lp-arrow" aria-hidden>→</span>
                </div>
              </a>
            ))}
          </div>
        </section>

        <section id="how" className="lp-wrap lp-section">
          <h2 className="reveal">사용 방법</h2>
          <p className="lp-lead reveal">화면은 한 번에 하나씩만 물어봐요. 단계를 눌러 직접 넘겨 볼 수도 있어요.</p>
          <div className="reveal"><StepDemo /></div>
        </section>

        <section id="roles" className="lp-wrap lp-section">
          <h2 className="reveal">직원과 검수 담당자 모두를 위해</h2>
          <div className="lp-roles">
            {ROLES.map((r, i) => (
              <article key={r.who} className={`lp-role ${r.kind} reveal`} style={{ transitionDelay: `${i * 90}ms` }}>
                {r.art}
                <div className="lp-role-body">
                  <span className="lp-tag">{r.who}</span>
                  <h3>{r.title}</h3>
                  <ul>{r.points.map((p) => <li key={p}>{p}</li>)}</ul>
                </div>
              </article>
            ))}
          </div>
        </section>

        <section id="stack" className="lp-wrap lp-section">
          <h2 className="reveal">AWS 위에서 동작해요</h2>
          <p className="lp-lead reveal">요청은 HTTPS 입구를 지나 EKS의 서비스로, 사진·분석·기록은 AWS 관리형 서비스로. 코드는 GitHub에서 자동으로 배포돼요.</p>
          <div className="reveal"><Architecture /></div>
        </section>

        <UsageSection />
      </main>

      <section className="lp-band">
        <div className="lp-wrap lp-band-row">
          <div>
            <h2>지금 첫 영수증을 올려 보세요</h2>
            <p>회사에서 받은 계정으로 로그인하면 바로 시작할 수 있어요.</p>
          </div>
          <Link to="/login" className="lp-pill lp-pill-light lp-pill-lg">로그인</Link>
        </div>
      </section>

      <footer className="lp-foot">
        <div className="lp-wrap lp-foot-row">
          <span className="brand lp-brand">receipt<span>flow</span></span>
          <span>© 2026 receiptflow · AWS 클라우드 AI 부트캠프 4팀</span>
        </div>
      </footer>
    </div>
  );
}
