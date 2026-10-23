import { useState } from "react";
import { Icon } from "./Icons";

// "만든 사람들": the four areas of the team (AGENTS.md "담당과 경계"), each with its GitHub profile.
// Static on purpose: the landing page is public and must not call the API for this.

const REPO = "https://github.com/aws-cloud-team4/receipt-flow";

type Member = {
  lead?: boolean;
  name: string;
  github: string;
  area: string;
  tone: "web" | "ai" | "api" | "infra";
  paths: string;
  work: string[];
};

const MEMBERS: Member[] = [
  {
    lead: true, name: "장차희", github: "CHAHEE03", area: "웹 화면·사용자 흐름", tone: "web", paths: "web/",
    work: ["직원·검수·관리자 화면", "촬영·테두리 보정 흐름", "AI 어시스턴트 대화 화면"],
  },
  {
    name: "김태희", github: "igwi292", area: "AI·데이터 처리", tone: "ai", paths: "ocr-worker · chat · preprocess",
    work: ["Bedrock 영수증 추출", "AI 어시스턴트 도구·응답 검사", "사진 보정·모델 평가"],
  },
  {
    name: "김수빈", github: "bb2002", area: "백엔드·DB", tone: "api", paths: "api-service · common",
    work: ["증빙·검수 API와 권한", "상태 전환·처리 이력", "DynamoDB 단일 테이블 설계"],
  },
  {
    name: "박준영", github: "nemm3623", area: "AWS·배포", tone: "infra", paths: "infra · deploy · .github",
    work: ["Terraform 인프라", "EKS 배포·자동 확장", "CI/CD·비용 알림"],
  },
];

function Avatar({ m }: { m: Member }) {
  const [failed, setFailed] = useState(false);
  return (
    <span className="lp-team-avatar" aria-hidden>
      {failed ? (
        <span className="lp-team-initial">{m.name.slice(-2)}</span>
      ) : (
        <img src={`https://github.com/${m.github}.png?size=160`} alt="" loading="lazy" width={64} height={64}
          onError={() => setFailed(true)} />
      )}
    </span>
  );
}

export default function TeamSection() {
  return (
    <section id="team" className="lp-wrap lp-section">
      <div className="lp-team-head">
        <div>
          <h2 className="reveal">만든 사람들</h2>
          <p className="lp-lead reveal">네 명이 영역을 나눠 맡고, 서로의 작업을 리뷰하며 만들었어요.</p>
        </div>
        <a className="lp-repo reveal" href={REPO} target="_blank" rel="noreferrer">
          <Icon name="git" />
          <span>팀 저장소 바로가기</span>
          <span aria-hidden>↗</span>
        </a>
      </div>
      <div className="lp-team">
        {MEMBERS.map((m, i) => (
          <a key={m.github} className={`lp-member ${m.tone} reveal`} style={{ transitionDelay: `${i * 80}ms` }}
            href={`https://github.com/${m.github}`} target="_blank" rel="noreferrer"
            aria-label={`${m.lead ? "조장" : "팀원"} ${m.name} — ${m.area}, GitHub 프로필 열기`}>
            <div className="lp-member-top">
              <Avatar m={m} />
              <span className={`lp-member-role${m.lead ? " lead" : ""}`}>{m.lead ? "조장" : "팀원"}</span>
            </div>
            <span className="lp-member-area">{m.area}</span>
            <h3>{m.name}</h3>
            <code className="lp-member-paths">{m.paths}</code>
            <ul>{m.work.map((w) => <li key={w}>{w}</li>)}</ul>
            <span className="lp-member-link">@{m.github} <span aria-hidden>↗</span></span>
          </a>
        ))}
      </div>
    </section>
  );
}
