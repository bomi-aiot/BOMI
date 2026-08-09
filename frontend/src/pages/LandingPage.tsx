import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import bomiAtmosphereUrl from '../assets/landing/bomi-atmosphere.webp'
import bomiRobotUrl from '../assets/landing/bomi-robot.webp'
import { Button } from '../components'
import { LandingDust } from '../components/landing/LandingDust'
import { LandingMotion } from '../components/landing/LandingMotion'
import './LandingPage.css'

const BomiHeroScene = lazy(() => import('../components/landing/BomiHeroScene'))

interface LandingPageProps {
  onNavigate: (path: string) => void
}

type SceneStatus = 'loading' | 'ready' | 'fallback'

// 호출 시나리오의 실제 3단계(웨이크워드 → Nav2 주행 → 사람 접근)를 그대로 옮긴 것.
const CALL_SEQUENCE = [
  {
    number: '01',
    title: '이름을 부르면 깨어납니다',
    description:
      '“보미야” 한마디를 알아듣습니다. 그 전까지는 아무것도 하지 않고, 부른 순간에만 대답합니다.',
  },
  {
    number: '02',
    title: '스스로 길을 찾아옵니다',
    description:
      '미리 그려 둔 집 지도 위에서 경로를 계산해 이동합니다. 오는 동안에는 말을 걸지 않습니다.',
  },
  {
    number: '03',
    title: '곁에 서서 이야기를 시작합니다',
    description:
      '카메라로 사람을 찾아 한 걸음 앞에 멈춰 섭니다. 마주 본 다음에야 대화가 시작됩니다.',
  },
]

// 시연 대상 4개 시나리오. 각 항목은 실제로 구현된 트리거를 설명한다.
const MOMENTS = [
  {
    number: '01',
    label: '호출',
    title: '부르면 거실로',
    description:
      '소파에서 “보미야” 하고 부르면 짧게 대답하고 곧장 이동합니다. 도착하면 다시 말을 겁니다.',
  },
  {
    number: '02',
    label: '귀가',
    title: '문이 열리면 현관으로',
    description:
      '문 열림 센서가 귀가를 알리면 현관까지 마중 나가 인사를 건네고 제자리로 돌아갑니다.',
  },
  {
    number: '03',
    label: '복약',
    title: '약 드실 시간에 맞춰',
    description:
      '정해 둔 복약 시간이 되면 곁으로 와서 말을 겁니다. 이미 한 알림을 다시 반복하지 않습니다.',
  },
  {
    number: '04',
    label: '환경',
    title: '방이 덥거나 습하면',
    description:
      '온도 30도, 습도 80%를 넘으면 센서가 알리고 보미가 찾아와 안부를 묻습니다.',
  },
]

// 카피가 추상적으로 흐르지 않도록 실제 하드웨어를 명시한다.
// where 는 "로봇에 달린 것"과 "집에 놓인 것"을 구분해 준다.
const SENSING = [
  {
    name: 'LiDAR',
    where: '로봇',
    desc: '집 구조를 스스로 익혀 머릿속에 지도를 그립니다.',
    effect: '가구를 옮겨도 다시 길을 찾습니다',
  },
  {
    name: '카메라',
    where: '로봇',
    desc: '사람이 어디 있는지 찾아 얼굴이 보이는 쪽에 섭니다.',
    effect: '등 뒤에서 말을 걸지 않습니다',
  },
  {
    name: '온습도·문열림 센서',
    where: '집',
    desc: '문이 열리는 순간과 방이 더워지는 순간을 알아챕니다.',
    effect: '부르지 않아도 먼저 찾아옵니다',
  },
  {
    name: '마이크·스피커',
    where: '로봇',
    desc: '어르신의 말을 듣고, 사람 목소리로 답합니다.',
    effect: '하루 중 보미가 가장 오래 하는 일입니다',
  },
]

// CONCEPTS.md §3.1·§3.3 의 설계 판단을 그대로 카피로 옮긴 것.
const PRINCIPLES = [
  [
    '침묵도 기능입니다',
    '스케줄러도 센서도 직접 말하지 못합니다. 전부 제안만 하고, 말할지 여부는 따로 판단합니다.',
  ],
  [
    '모르면 모른다고 합니다',
    '재지 못한 값을 0으로 적지 않습니다. 틀린 알림이 쌓이면 정작 급할 때 그 알림을 믿지 않게 되니까요.',
  ],
  [
    '판단은 사람에게 남깁니다',
    '보미는 진단하지 않습니다. 관찰한 맥락을 정리해 보호자에게 전하는 데까지가 역할입니다.',
  ],
]

export function LandingPage({ onNavigate }: LandingPageProps) {
  const pageRef = useRef<HTMLDivElement>(null)
  const [sceneStatus, setSceneStatus] = useState<SceneStatus>('loading')

  const handleSceneStatus = useCallback((status: 'ready' | 'fallback') => {
    setSceneStatus(status)
  }, [])

  // 섹션 스냅과 부드러운 앵커 이동은 html 에 걸어야 동작한다. 대시보드가 같은 html 을
  // 공유하므로 랜딩이 떠 있는 동안에만 붙이고 언마운트 때 반드시 되돌린다.
  useEffect(() => {
    const root = document.documentElement
    root.classList.add('landing-snap')
    return () => root.classList.remove('landing-snap')
  }, [])

  useEffect(() => {
    const page = pageRef.current
    if (!page) return

    const items = Array.from(page.querySelectorAll<HTMLElement>('[data-landing-reveal]'))
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

    if (reducedMotion || !('IntersectionObserver' in window)) {
      items.forEach((item) => item.classList.add('is-visible'))
      return
    }

    // 임계값이 높으면 카드가 화면에 들어온 뒤에도 한참 비어 있어 스크롤이 멈춘 것처럼 보인다.
    // 아주 조금만 걸쳐도 바로 드러나게 한다.
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting && entry.boundingClientRect.top > window.innerHeight) return
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        })
      },
      { rootMargin: '0px 0px -2% 0px', threshold: 0.01 },
    )

    items.forEach((item) => observer.observe(item))
    return () => observer.disconnect()
  }, [])

  return (
    <div ref={pageRef} className="landing-page">
      <a className="skip-link" href="#landing-main">본문으로 바로가기</a>

      <header className="landing-header" aria-label="BOMI 랜딩 헤더">
        <button
          className="landing-brand"
          type="button"
          onClick={() => onNavigate('/')}
          aria-label="BOMI 홈"
        >
          <span className="landing-brand__mark" aria-hidden="true">B</span>
          <span className="landing-brand__wordmark">
            <strong>BOMI</strong>
            <small>care companion</small>
          </span>
        </button>
      </header>

      <main id="landing-main" tabIndex={-1}>
        <section
          className="landing-hero"
          aria-labelledby="landing-title"
          data-buddy-dock="left"
          data-buddy-say="안녕하세요, 보미예요"
        >
          <div className="landing-hero__wash" aria-hidden="true" />

          <div className="landing-hero__copy">
            <p className="landing-eyebrow landing-stage landing-stage--1">
              <span aria-hidden="true" />
              집 안을 스스로 다니는 돌봄 로봇
            </p>
            <h1 id="landing-title" className="landing-stage landing-stage--2">
              부르면,
              <span>찾아옵니다.</span>
            </h1>
            <p className="landing-hero__description landing-stage landing-stage--3">
              “보미야” 한마디면 보미가 스스로 길을 찾아 어르신 곁으로 옵니다.
              문이 열릴 때도, 약 드실 시간에도, 방이 더울 때도 먼저 다가가 말을 겁니다.
            </p>
            <div className="landing-hero__actions landing-stage landing-stage--4">
              <Button
                size="large"
                className="landing-primary-cta"
                onClick={() => onNavigate('/bomi-home')}
              >
                보호자 웹 만나보기
              </Button>
              <a className="landing-ghost-cta" href="#landing-call">
                보미가 오는 길 보기
                <span aria-hidden="true">↓</span>
              </a>
            </div>
            <div className="landing-hero__note landing-stage landing-stage--5" aria-label="보미 서비스 특징">
              <span className="landing-hero__note-mark" aria-hidden="true">♥</span>
              <p><strong>말동무가 되는 일이 먼저입니다.</strong> 혼자 계시는 시간이 가장 걱정되니까요.</p>
            </div>
          </div>

          <figure className={`landing-hero__visual landing-hero__visual--${sceneStatus}`}>
            <img
              className="landing-hero__atmosphere"
              src={bomiAtmosphereUrl}
              alt=""
              aria-hidden="true"
              draggable="false"
            />
            <div className="landing-hero__halo" aria-hidden="true" />
            <img
              className="landing-hero__robot-fallback"
              src={bomiRobotUrl}
              width="651"
              height="881"
              alt="분홍색 돌봄 로봇 보미가 환하게 웃고 있는 모습"
              decoding="async"
              fetchPriority="high"
              draggable="false"
            />
            <Suspense fallback={null}>
              <BomiHeroScene onStatusChange={handleSceneStatus} />
            </Suspense>
            <span className="landing-orbit-label landing-orbit-label--talk" aria-hidden="true">
              <i /> “보미야” 인식
            </span>
            <span className="landing-orbit-label landing-orbit-label--care" aria-hidden="true">
              <i /> 스스로 이동
            </span>
            <figcaption>
              <span>MOVE TO MEET BOMI</span>
              눈을 맞추면 표정이 따라와요
            </figcaption>
          </figure>

          <a className="landing-scroll-cue" href="#landing-call" aria-label="보미가 오는 과정으로 이동">
            <span aria-hidden="true" />
            SCROLL TO DISCOVER
          </a>
        </section>

        <section
          id="landing-call"
          className="landing-call"
          aria-labelledby="landing-call-title"
          data-buddy-dock="right"
          data-buddy-say="부르시면 어디든 갈게요"
        >
          <div className="landing-call__intro" data-landing-reveal>
            <p className="landing-eyebrow"><span aria-hidden="true" /> 부르고 난 다음</p>
            <h2 id="landing-call-title">
              <span className="landing-rv"><span>“보미야”</span></span>
              <span className="landing-rv landing-rv--accent"><span>한마디면 충분합니다.</span></span>
            </h2>
            <p>
              부르는 순간부터 곁에 설 때까지, 보미가 알아서 합니다.
              어르신이 하실 일은 이름을 부르는 것뿐입니다.
            </p>
            <button type="button" className="landing-call__try">
              “보미야” 하고 불러보기 <span aria-hidden="true">♥</span>
            </button>
          </div>

          <ol className="landing-call__steps">
            {CALL_SEQUENCE.map((step, index) => (
              <li
                key={step.number}
                data-landing-reveal
                style={{ '--landing-delay': `${index * 80}ms` } as React.CSSProperties}
              >
                <span className="landing-call__number" aria-hidden="true">{step.number}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section
          id="landing-moments"
          className="landing-day"
          aria-labelledby="landing-day-title"
          data-buddy-dock="left"
          data-buddy-say="제가 먼저 다가갈게요"
        >
          <div className="landing-section-heading" data-landing-reveal>
            <p className="landing-eyebrow"><span aria-hidden="true" /> 보미가 먼저 움직이는 순간</p>
            <h2 id="landing-day-title">
              <span className="landing-rv"><span>기다리지 않고</span></span>
              <span className="landing-rv"><span>먼저 다가갑니다</span></span>
            </h2>
            <p>부를 때만이 아니라, 집이 보내는 신호에도 보미가 스스로 움직입니다.</p>
          </div>

          <ol className="landing-day__steps">
            {MOMENTS.map((moment, index) => (
              <li
                key={moment.number}
                data-landing-reveal
                style={{ '--landing-delay': `${index * 70}ms` } as React.CSSProperties}
              >
                <div className="landing-day__number" aria-hidden="true">{moment.number}</div>
                <span className="landing-day__label">{moment.label}</span>
                <h3>{moment.title}</h3>
                <p>{moment.description}</p>
                <span className="landing-day__line" aria-hidden="true" />
              </li>
            ))}
          </ol>
        </section>

        <section
          className="landing-sensing"
          aria-labelledby="landing-sensing-title"
          data-buddy-dock="right"
          data-buddy-say="집이 보내는 신호를 듣고 있어요"
        >
          <div className="landing-sensing__lead" data-landing-reveal>
            <p className="landing-eyebrow"><span aria-hidden="true" /> 보미가 집을 읽는 방법</p>
            <h2 id="landing-sensing-title">
              <span className="landing-rv"><span>집을 읽는 네 가지 감각</span></span>
            </h2>
            <p>
              보미가 길을 찾고 사람을 알아보는 일은 전부 센서에서 시작합니다.
              무엇으로 보고 듣는지 그대로 적었습니다.
            </p>
          </div>

          <ul className="landing-sensing__list">
            {SENSING.map((item, index) => (
              <li
                key={item.name}
                data-landing-reveal
                style={{ '--landing-delay': `${index * 70}ms` } as React.CSSProperties}
              >
                <span className="landing-sensing__where">{item.where}</span>
                <strong>{item.name}</strong>
                <p>{item.desc}</p>
                <p className="landing-sensing__effect">{item.effect}</p>
              </li>
            ))}
          </ul>

          <p className="landing-sensing__closing" data-landing-reveal>
            이 모든 건 어르신이 부르기 전에
            <strong>먼저 알아차리기 위한 것입니다.</strong>
          </p>

          <p className="landing-sensing__stack" data-landing-reveal>
            ROS 2 Humble · Nav2 · SLAM Toolbox · Jetson Orin Nano
          </p>
        </section>

        <section
          className="landing-human"
          aria-labelledby="landing-human-title"
          data-buddy-dock="left"
          data-buddy-say="말하지 않을 때도 곁에 있어요"
        >
          <div className="landing-human__glow" aria-hidden="true" />
          <LandingDust />
          <div className="landing-human__statement" data-landing-reveal>
            <p className="landing-eyebrow landing-eyebrow--light"><span aria-hidden="true" /> HUMAN FIRST</p>
            <h2 id="landing-human-title">
              <span className="landing-rv"><span>많이 말하는 로봇이</span></span>
              <span className="landing-rv landing-rv--accent"><span>좋은 로봇은 아닙니다.</span></span>
            </h2>
            <p>
              울릴 때마다 말하는 로봇은 잔소리꾼이 됩니다. 새벽에 떠들고, 보시던 TV 를 끊고,
              방금 한 알림을 또 합니다. 그래서 보미는 무엇을 말할지보다 말할지 여부를 먼저 정합니다.
            </p>
          </div>

          <ul className="landing-human__principles">
            {PRINCIPLES.map(([title, description], index) => (
              <li
                key={title}
                data-landing-reveal
                style={{ '--landing-delay': `${100 + index * 80}ms` } as React.CSSProperties}
              >
                <span aria-hidden="true">0{index + 1}</span>
                <div><strong>{title}</strong><p>{description}</p></div>
              </li>
            ))}
          </ul>
        </section>

        <section
          className="landing-final"
          aria-labelledby="landing-final-title"
          data-buddy-dock="right"
          data-buddy-say="내일도 함께할게요"
        >
          <div className="landing-final__rings" aria-hidden="true"><span /><span /><span /></div>
          <div className="landing-final__content" data-landing-reveal>
            <p className="landing-eyebrow"><span aria-hidden="true" /> 오늘부터 이어지는 돌봄</p>
            <h2 id="landing-final-title">
              <span className="landing-rv"><span>곁에 있지 못한 날에도,</span></span>
              <span className="landing-rv"><span>오늘을 알 수 있도록.</span></span>
            </h2>
            <p>보미가 만난 순간들이 보호자 웹에 하루 단위로 정리됩니다.</p>
            <Button
              size="large"
              className="landing-primary-cta landing-final__cta"
              onClick={() => onNavigate('/bomi-home')}
            >
              보호자 웹 시작하기
            </Button>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="landing-brand landing-brand--footer" aria-label="BOMI">
          <span className="landing-brand__mark" aria-hidden="true">B</span>
          <span className="landing-brand__wordmark"><strong>BOMI</strong><small>care companion</small></span>
        </div>
        <p>기술로 연결하고, 마음으로 돌봅니다.</p>
        <small>© 2026 BOMI. All rights reserved.</small>
      </footer>

      <LandingMotion pageRef={pageRef} />
    </div>
  )
}
