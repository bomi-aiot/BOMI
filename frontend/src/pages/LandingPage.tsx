import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import bomiAtmosphereUrl from '../assets/landing/bomi-atmosphere.webp'
import bomiRobotUrl from '../assets/landing/bomi-robot.webp'
import { Button } from '../components'
import './LandingPage.css'

const BomiHeroScene = lazy(() => import('../components/landing/BomiHeroScene'))

interface LandingPageProps {
  onNavigate: (path: string) => void
}

type SceneStatus = 'loading' | 'ready' | 'fallback'

const DAY_STEPS = [
  {
    number: '01',
    label: '돌봄',
    title: '필요한 순간에 곁으로',
    description: '익숙한 공간에서 이어지는 하루를 존중하며, 보미는 필요한 순간을 함께합니다.',
  },
  {
    number: '02',
    label: '일정',
    title: '오늘의 약속을 다정하게',
    description: '복약과 일정처럼 잊기 쉬운 약속을 부담스럽지 않은 방식으로 다시 건넵니다.',
  },
  {
    number: '03',
    label: '대화',
    title: '말을 건네고 마음을 듣고',
    description: '정답을 재촉하기보다 일상의 말벗이 되어 편안한 대화의 시간을 만듭니다.',
  },
  {
    number: '04',
    label: '연결',
    title: '가족의 마음까지 이어지게',
    description: '공유하기로 한 정보만 정리해 보호자가 오늘의 맥락을 이해하도록 돕습니다.',
  },
]

const HUMAN_FIRST_PRINCIPLES = [
  ['존중', '어르신의 익숙한 생활 방식과 선택을 먼저 생각합니다.'],
  ['맥락', '기록을 단정적인 결론으로 바꾸지 않고, 관찰된 맥락을 전합니다.'],
  ['연결', '기술이 관계를 대신하지 않고 가족의 대화를 이어 주도록 설계합니다.'],
]

export function LandingPage({ onNavigate }: LandingPageProps) {
  const pageRef = useRef<HTMLDivElement>(null)
  const [sceneStatus, setSceneStatus] = useState<SceneStatus>('loading')

  const handleSceneStatus = useCallback((status: 'ready' | 'fallback') => {
    setSceneStatus(status)
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

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting && entry.boundingClientRect.top > window.innerHeight) return
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        })
      },
      { rootMargin: '0px 0px -12% 0px', threshold: 0.12 },
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
        <Button
          variant="secondary"
          size="small"
          className="landing-header__cta"
          onClick={() => onNavigate('/bomi-home')}
        >
          보호자 웹 시작하기
        </Button>
      </header>

      <main id="landing-main" tabIndex={-1}>
        <section className="landing-hero" aria-labelledby="landing-title">
          <div className="landing-hero__wash" aria-hidden="true" />

          <div className="landing-hero__copy">
            <p className="landing-eyebrow">
              <span aria-hidden="true" />
              일상 가까이, 마음 가까이
            </p>
            <h1 id="landing-title">
              돌봄의 매일에,
              <span>보미가 함께.</span>
            </h1>
            <p className="landing-hero__description">
              다정한 대화부터 오늘의 일정까지. 보미는 어르신의 익숙한 하루를 존중하고,
              가족의 마음이 자연스럽게 이어지도록 돕습니다.
            </p>
            <div className="landing-hero__actions">
              <Button
                size="large"
                className="landing-primary-cta"
                onClick={() => onNavigate('/bomi-home')}
              >
                보호자 웹 만나보기
              </Button>
              <a className="landing-secondary-link" href="#landing-day">
                보미의 하루 살펴보기
                <span aria-hidden="true">↓</span>
              </a>
            </div>
            <div className="landing-hero__note" aria-label="보미 서비스 특징">
              <span className="landing-hero__note-mark" aria-hidden="true">♥</span>
              <p><strong>기술보다 사람을 먼저.</strong> 따뜻한 돌봄 경험을 만듭니다.</p>
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
              <i /> 다정한 대화
            </span>
            <span className="landing-orbit-label landing-orbit-label--care" aria-hidden="true">
              <i /> 이어지는 돌봄
            </span>
            <figcaption>
              <span>MOVE TO MEET BOMI</span>
              눈을 맞추면 표정이 따라와요
            </figcaption>
          </figure>

          <a className="landing-scroll-cue" href="#landing-day" aria-label="보미가 함께하는 하루로 이동">
            <span aria-hidden="true" />
            SCROLL TO DISCOVER
          </a>
        </section>

        <section id="landing-day" className="landing-day" aria-labelledby="landing-day-title">
          <div className="landing-section-heading" data-landing-reveal>
            <p className="landing-eyebrow"><span aria-hidden="true" /> 보미가 함께하는 하루</p>
            <h2 id="landing-day-title">평범한 하루의 순간들이<br />따뜻한 연결이 되도록</h2>
            <p>돌봄, 일정, 대화, 연결. 네 가지 마음을 한 흐름으로 이어 갑니다.</p>
          </div>

          <ol className="landing-day__steps">
            {DAY_STEPS.map((step, index) => (
              <li
                key={step.number}
                data-landing-reveal
                style={{ '--landing-delay': `${index * 90}ms` } as React.CSSProperties}
              >
                <div className="landing-day__number" aria-hidden="true">{step.number}</div>
                <span className="landing-day__label">{step.label}</span>
                <h3>{step.title}</h3>
                <p>{step.description}</p>
                <span className="landing-day__line" aria-hidden="true" />
              </li>
            ))}
          </ol>
        </section>

        <section className="landing-human" aria-labelledby="landing-human-title">
          <div className="landing-human__glow" aria-hidden="true" />
          <div className="landing-human__statement" data-landing-reveal>
            <p className="landing-eyebrow landing-eyebrow--light"><span aria-hidden="true" /> HUMAN FIRST</p>
            <h2 id="landing-human-title">
              더 많은 기술보다,
              <span>더 사람다운 방식.</span>
            </h2>
            <p>
              보미는 일상을 대신 판단하지 않습니다. 필요한 정보가 닿도록 돕고,
              돌봄의 결정은 사람 사이에서 이어지도록 설계합니다.
            </p>
          </div>

          <ul className="landing-human__principles">
            {HUMAN_FIRST_PRINCIPLES.map(([title, description], index) => (
              <li
                key={title}
                data-landing-reveal
                style={{ '--landing-delay': `${120 + index * 90}ms` } as React.CSSProperties}
              >
                <span aria-hidden="true">0{index + 1}</span>
                <div><strong>{title}</strong><p>{description}</p></div>
              </li>
            ))}
          </ul>
        </section>

        <section className="landing-final" aria-labelledby="landing-final-title">
          <div className="landing-final__rings" aria-hidden="true"><span /><span /><span /></div>
          <div className="landing-final__content" data-landing-reveal>
            <p className="landing-eyebrow"><span aria-hidden="true" /> 오늘부터 이어지는 돌봄</p>
            <h2 id="landing-final-title">가까이 있지 않아도,<br />마음은 이어질 수 있도록.</h2>
            <p>보미 보호자 웹에서 오늘의 돌봄 흐름을 차분하게 살펴보세요.</p>
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
    </div>
  )
}
