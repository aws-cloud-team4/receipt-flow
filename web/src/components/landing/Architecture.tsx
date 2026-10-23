import { Icon, type IconName } from "./Icons";

// "AWS 위에서 동작해요": request path left to right (사용자 → 입구 → EKS → 데이터·AI) and the
// delivery path underneath (GitHub → Actions → ECR → EKS). Boxes with line icons and arrows;
// reflows to a single column on phones.

type Item = { name: string; role: string; icon: IconName };

const SERVICES: Item[] = [
  { name: "web", role: "화면", icon: "window" },
  { name: "api-service", role: "증빙·검수·상태", icon: "api" },
  { name: "chat-service", role: "AI 어시스턴트", icon: "chat" },
  { name: "preprocess", role: "사진 테두리·보정", icon: "crop" },
  { name: "ocr-worker", role: "AI 추출·점검", icon: "worker" },
];

const DATA: Item[] = [
  { name: "Amazon S3", role: "원본·보정 사진", icon: "bucket" },
  { name: "Amazon SQS", role: "분석 대기열 · 실패 큐", icon: "queue" },
  { name: "Amazon Bedrock", role: "영수증 추출 · 대화", icon: "spark" },
  { name: "Amazon DynamoDB", role: "증빙 · 대화 · 처리 이력", icon: "db" },
];

const DELIVERY: Item[] = [
  { name: "GitHub", role: "PR · 코드 리뷰", icon: "git" },
  { name: "GitHub Actions", role: "빌드 · 테스트", icon: "play" },
  { name: "Amazon ECR", role: "컨테이너 이미지", icon: "stack" },
  { name: "Amazon EKS", role: "main에 머지하면 자동 배포", icon: "cluster" },
];

const NOTES = [
  "사진은 브라우저에서 S3로 바로 올라가고, 올라오면 SQS에 분석 작업이 쌓여요.",
  "ocr-worker가 대기열에서 꺼내 Bedrock으로 칸을 읽고, 점검 결과와 함께 DynamoDB에 저장해요.",
  "AI 어시스턴트 대화는 chat-service가 Bedrock으로 답하고, 바꾼 칸은 처리 이력에 남겨요.",
  "서비스마다 부하에 따라 Pod가 늘고 줄며, 분석 워커는 대기열 길이에 맞춰 늘어나요.",
];

function Box({ name, role, icon, strong }: Item & { strong?: boolean }) {
  return (
    <div className={`arch-box${strong ? " strong" : ""}`}>
      <span className="arch-ico-wrap"><Icon name={icon} /></span>
      <span className="arch-txt">
        <b>{name}</b>
        <span>{role}</span>
      </span>
    </div>
  );
}

export default function Architecture() {
  return (
    <div className="arch">
      <div className="arch-run">
        <div className="arch-group">
          <div className="arch-label">사용자</div>
          <Box name="직원" role="휴대폰으로 촬영·제출" icon="phone" />
          <Box name="검수 담당자" role="PC에서 검토·승인" icon="monitor" />
          <Box name="Amazon Cognito" role="로그인 · 역할" icon="lock" strong />
        </div>

        <div className="arch-arrow" aria-hidden><span>HTTPS</span></div>

        <div className="arch-group">
          <div className="arch-label">입구</div>
          <Box name="Amazon CloudFront" role="HTTPS 주소" icon="globe" strong />
          <Box name="Application Load Balancer" role="/api · /chat · /preprocess 로 나눔" icon="split" strong />
        </div>

        <div className="arch-arrow" aria-hidden />

        <div className="arch-group arch-eks">
          <div className="arch-label">Amazon EKS <em>Pod·노드 자동 확장</em></div>
          <div className="arch-svc">
            {SERVICES.map((s) => <Box key={s.name} {...s} />)}
          </div>
        </div>

        <div className="arch-arrow" aria-hidden />

        <div className="arch-group">
          <div className="arch-label">데이터 · AI</div>
          {DATA.map((d) => <Box key={d.name} {...d} strong />)}
        </div>
      </div>

      <div className="arch-cicd">
        <div className="arch-label">자동 배포 · main에 머지하면</div>
        <ol>
          {DELIVERY.map((d) => (
            <li key={d.name}><Box {...d} strong={d.name.startsWith("Amazon")} /></li>
          ))}
        </ol>
      </div>

      <ol className="arch-notes">
        {NOTES.map((n) => <li key={n}>{n}</li>)}
      </ol>
    </div>
  );
}
