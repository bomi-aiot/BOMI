import { Button } from '../components'

interface LandingPageProps {
  onNavigate: (path: string) => void
}

export function LandingPage({ onNavigate }: LandingPageProps) {
  return (
    <div className="landing-page">
      <a className="skip-link" href="#landing-main">본문으로 바로가기</a>
      <header className="landing-header">
        <button className="landing-brand" type="button" onClick={() => onNavigate('/')} aria-label="BOMI 홈">
          <span aria-hidden="true">B</span>
          <strong>BOMI</strong>
        </button>
        <Button variant="secondary" size="small" onClick={() => onNavigate('/dashboard')}>
          보호자 화면
        </Button>
      </header>

      <main id="landing-main" tabIndex={-1}>
        <section className="landing-hero" aria-labelledby="landing-title">
          <div className="landing-ambient" aria-hidden="true">
            <span className="landing-ambient__room" />
            <span className="landing-ambient__path" />
            <span className="landing-ambient__point landing-ambient__point--door" />
            <span className="landing-ambient__point landing-ambient__point--care" />
            <span className="landing-ambient__point landing-ambient__point--home" />
            <span className="landing-ambient__pulse" />
          </div>
          <div className="landing-hero__copy">
            <p className="landing-kicker">집의 하루가 안심으로 이어지는 길</p>
            <h1 id="landing-title">멀리 있어도,<br />오늘을 함께 돌봅니다.</h1>
            <p>
              보미는 필요한 순간 어르신 곁으로 다가가고, 보호자에게는
              꼭 필요한 맥락만 전합니다.
            </p>
            <Button size="large" onClick={() => onNavigate('/dashboard')}>
              오늘의 돌봄 확인하기
            </Button>
          </div>
          <div className="landing-hero__signal" aria-hidden="true">
            <span>BOMI</span>
            <strong>조용히 곁을 지키는 돌봄</strong>
            <small>일정 · 복약 알림 · 보호자 확인</small>
          </div>
        </section>

        <section className="landing-story" aria-labelledby="landing-story-title">
          <div className="landing-story__intro">
            <p className="landing-kicker">보호자에게 필요한 네 가지</p>
            <h2 id="landing-story-title">한눈에 판단하고,<br />다음 행동까지 이어지도록</h2>
          </div>
          <ol className="landing-story__steps">
            <li><span>01</span><strong>지금 확인할 일</strong><p>실제 안전 확인 요청이 있을 때만 가장 먼저 알려드려요.</p></li>
            <li><span>02</span><strong>오늘의 변화</strong><p>공유가 허용된 기록과 근거 시각을 함께 보여드려요.</p></li>
            <li><span>03</span><strong>다음 돌봄</strong><p>확정된 일정과 복약 응답을 과장 없이 정리해요.</p></li>
            <li><span>04</span><strong>마지막 관찰</strong><p>요약 생성 시각과 실제 관측 시각을 구분해요.</p></li>
          </ol>
        </section>

        <section className="landing-trust" aria-labelledby="landing-trust-title">
          <div>
            <p className="landing-kicker">안심의 원칙</p>
            <h2 id="landing-trust-title">많이 보여주는 것보다<br />정확하게 전하는 것</h2>
          </div>
          <ul>
            <li>비공개 대화와 원문은 보호자 화면에 표시하지 않아요.</li>
            <li>응답 없음은 미복용이나 위험으로 단정하지 않아요.</li>
            <li>확인 전 정보는 확정된 돌봄 계획과 분리해요.</li>
          </ul>
          <Button onClick={() => onNavigate('/dashboard')}>보호자 화면 시작하기</Button>
        </section>
      </main>
    </div>
  )
}
