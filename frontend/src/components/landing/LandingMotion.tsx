import { useEffect, useRef } from 'react'
import bomiRobotUrl from '../../assets/landing/bomi-robot.webp'

interface LandingMotionProps {
  pageRef: React.RefObject<HTMLDivElement | null>
}

interface DockPoint {
  x: number
  y: number
}

const BUDDY_W = 86
// 미니 보미는 콘텐츠 위를 떠다니므로 좁은 화면에서는 본문을 가린다. 데스크톱 폭에서만 켠다.
const BUDDY_MIN_VIEWPORT = 900

/**
 * 랜딩 전용 모션 레이어. 세 가지를 담당한다.
 *  - 커서 점·링(전 구간)과 CTA 마그네틱, 카드 틸트
 *  - 미니 보미 동행: 섹션마다 스프링 물리로 이동하며 말풍선으로 한마디씩
 *  - "보미야" 호출 데모: 버튼을 누르면 미니 보미가 실제로 달려온다
 *
 * 전부 pointer:fine + 모션 허용 환경에서만 동작하고, 언마운트 시 리스너·rAF·클래스를
 * 모두 되돌린다(대시보드와 html 을 공유하므로 잔류 금지).
 */
export function LandingMotion({ pageRef }: LandingMotionProps) {
  const dotRef = useRef<HTMLDivElement>(null)
  const ringRef = useRef<HTMLDivElement>(null)
  const buddyRef = useRef<HTMLDivElement>(null)
  const bubbleRef = useRef<HTMLSpanElement>(null)

  useEffect(() => {
    const page = pageRef.current
    const dot = dotRef.current
    const ring = ringRef.current
    const buddy = buddyRef.current
    const bubble = bubbleRef.current
    if (!page || !dot || !ring || !buddy || !bubble) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const finePointer = window.matchMedia('(pointer: fine)').matches
    if (reduced || !finePointer) return

    page.classList.add('landing-motion-on')
    let buddyOn = window.innerWidth >= BUDDY_MIN_VIEWPORT
    page.classList.toggle('landing-buddy-on', buddyOn)

    const cleanups: Array<() => void> = []
    const timeouts: Array<ReturnType<typeof setTimeout>> = []
    const later = (fn: () => void, ms: number) => {
      timeouts.push(setTimeout(fn, ms))
    }

    /* ── 포인터 추적 (커서 점·링) ─────────────────────────── */
    let mx = -120
    let my = -120
    let ringX = -120
    let ringY = -120
    let ringScale = 1
    let ringTarget = 1
    const onMove = (e: PointerEvent) => {
      mx = e.clientX
      my = e.clientY
    }
    window.addEventListener('pointermove', onMove, { passive: true })
    cleanups.push(() => window.removeEventListener('pointermove', onMove))

    const HOT = 'a, button, .landing-day__steps > li, .landing-sensing__list > li'
    const onOver = (e: PointerEvent) => {
      const target = e.target as Element | null
      const hot = Boolean(target && target.closest(HOT))
      ringTarget = hot ? 1.7 : 1
      ring.classList.toggle('is-hot', hot)
    }
    page.addEventListener('pointerover', onOver)
    cleanups.push(() => page.removeEventListener('pointerover', onOver))

    /* ── CTA 마그네틱 ─────────────────────────────────────── */
    page
      .querySelectorAll<HTMLElement>('.landing-primary-cta, .landing-ghost-cta, .landing-call__try')
      .forEach((el) => {
        let raf = 0
        const move = (e: PointerEvent) => {
          const r = el.getBoundingClientRect()
          const dx = e.clientX - (r.left + r.width / 2)
          const dy = e.clientY - (r.top + r.height / 2)
          cancelAnimationFrame(raf)
          raf = requestAnimationFrame(() => {
            el.style.transform = `translate(${dx * 0.16}px, ${dy * 0.2}px)`
          })
        }
        const leave = () => {
          cancelAnimationFrame(raf)
          el.style.transition = 'transform 340ms cubic-bezier(0.2, 0.72, 0.2, 1)'
          el.style.transform = ''
          later(() => {
            el.style.transition = ''
          }, 360)
        }
        el.addEventListener('pointermove', move)
        el.addEventListener('pointerleave', leave)
        cleanups.push(() => {
          cancelAnimationFrame(raf)
          el.removeEventListener('pointermove', move)
          el.removeEventListener('pointerleave', leave)
          el.style.transform = ''
          el.style.transition = ''
        })
      })

    /* ── 카드 틸트 ────────────────────────────────────────── */
    page
      .querySelectorAll<HTMLElement>('.landing-day__steps > li, .landing-sensing__list > li')
      .forEach((card) => {
        let raf = 0
        const move = (e: PointerEvent) => {
          const r = card.getBoundingClientRect()
          const px = (e.clientX - r.left) / r.width
          const py = (e.clientY - r.top) / r.height
          card.style.setProperty('--landing-mx', `${px * 100}%`)
          card.style.setProperty('--landing-my', `${py * 100}%`)
          cancelAnimationFrame(raf)
          raf = requestAnimationFrame(() => {
            card.style.transform = `perspective(720px) rotateX(${(py - 0.5) * -8}deg) rotateY(${(px - 0.5) * 9}deg) translateY(-4px)`
          })
        }
        const leave = () => {
          cancelAnimationFrame(raf)
          card.style.transition = 'transform 380ms ease, box-shadow 280ms ease'
          card.style.transform = ''
          later(() => {
            card.style.transition = ''
          }, 400)
        }
        card.addEventListener('pointermove', move)
        card.addEventListener('pointerleave', leave)
        cleanups.push(() => {
          cancelAnimationFrame(raf)
          card.removeEventListener('pointermove', move)
          card.removeEventListener('pointerleave', leave)
          card.style.transform = ''
          card.style.transition = ''
        })
      })

    /* ── 미니 보미: 섹션 도킹 + 말풍선 ────────────────────── */
    const sections = Array.from(page.querySelectorAll<HTMLElement>('main > section'))
    const dockFor = (sec: HTMLElement): DockPoint => {
      const side = sec.dataset.buddyDock ?? 'right'
      const x =
        side === 'left'
          ? 96
          : side === 'center'
            ? window.innerWidth * 0.5 - 180
            : window.innerWidth - 150
      return { x, y: window.innerHeight - 152 }
    }

    let active: HTMLElement | null = sections[0] ?? null
    let dock: DockPoint = active ? dockFor(active) : { x: 96, y: window.innerHeight - 152 }
    // 화면 아래에서 첫 도킹 지점으로 "걸어 들어오는" 등장
    let bx = dock.x
    let by = window.innerHeight + 140
    let bvx = 0
    let bvy = 0
    let calling = false

    const say = (text: string, ms = 2000) => {
      if (!buddyOn || !text) return
      bubble.textContent = text
      bubble.classList.add('is-show')
      later(() => bubble.classList.remove('is-show'), ms)
    }

    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return
          active = entry.target as HTMLElement
          if (!calling) {
            dock = dockFor(active)
            say(active.dataset.buddySay ?? '')
          }
        })
      },
      { threshold: 0.55 },
    )
    sections.forEach((s) => io.observe(s))
    cleanups.push(() => io.disconnect())

    const onResize = () => {
      buddyOn = window.innerWidth >= BUDDY_MIN_VIEWPORT
      page.classList.toggle('landing-buddy-on', buddyOn)
      if (active) dock = dockFor(active)
    }
    window.addEventListener('resize', onResize)
    cleanups.push(() => window.removeEventListener('resize', onResize))

    /* ── 하트 버스트 ──────────────────────────────────────── */
    const burst = (x: number, y: number) => {
      for (let i = 0; i < 9; i += 1) {
        const heart = document.createElement('div')
        heart.className = 'landing-heart'
        heart.textContent = '♥'
        heart.style.left = `${x}px`
        heart.style.top = `${y}px`
        heart.style.color = i % 2 ? '#ef397f' : '#ffb4cf'
        page.appendChild(heart)
        const angle = Math.random() * Math.PI * 2
        const dist = 40 + Math.random() * 60
        heart
          .animate(
            [
              { transform: 'translate(0, 0) scale(1)', opacity: 1 },
              {
                transform: `translate(${Math.cos(angle) * dist}px, ${Math.sin(angle) * dist - 48}px) scale(0.4)`,
                opacity: 0,
              },
            ],
            { duration: 820 + Math.random() * 380, easing: 'cubic-bezier(0.2, 0.72, 0.2, 1)' },
          )
          .addEventListener('finish', () => heart.remove())
      }
    }

    const onBuddyClick = () => {
      say('만나서 반가워요!')
      burst(bx + BUDDY_W / 2, by + 8)
    }
    buddy.addEventListener('click', onBuddyClick)
    cleanups.push(() => buddy.removeEventListener('click', onBuddyClick))

    /* ── "보미야" 호출 데모 ───────────────────────────────── */
    const callBtn = page.querySelector<HTMLElement>('.landing-call__try')
    const onCall = () => {
      if (!buddyOn) {
        burst(mx, my)
        return
      }
      if (calling || !callBtn) return
      calling = true
      const r = callBtn.getBoundingClientRect()
      dock = {
        x: Math.min(window.innerWidth - 120, r.right + 26),
        y: Math.max(90, r.top - 20),
      }
      say('네, 지금 갈게요!', 1400)
      later(() => {
        say('불러 주셔서 왔어요 ♥', 1800)
        burst(dock.x + BUDDY_W / 2, dock.y + 16)
      }, 950)
      later(() => {
        calling = false
        if (active) dock = dockFor(active)
      }, 3200)
    }
    callBtn?.addEventListener('click', onCall)
    if (callBtn) cleanups.push(() => callBtn.removeEventListener('click', onCall))

    /* ── 메인 루프: 커서 lerp + 버디 스프링 ───────────────── */
    let raf = 0
    const tick = (time: number) => {
      dot.style.transform = `translate(${mx - 4}px, ${my - 4}px)`
      ringX += (mx - ringX) * 0.16
      ringY += (my - ringY) * 0.16
      ringScale += (ringTarget - ringScale) * 0.2
      ring.style.transform = `translate(${ringX - 17}px, ${ringY - 17}px) scale(${ringScale})`

      if (buddyOn) {
        // 도킹 지점 기준으로 커서 쪽에 살짝 끌리게 — "따라다니는" 감각의 실체
        const pull = Math.max(-34, Math.min(34, (mx - dock.x) * 0.05))
        bvx += (dock.x + pull - bx) * 0.012
        bvy += (dock.y - by) * 0.012
        bvx *= 0.88
        bvy *= 0.88
        bx += bvx
        by += bvy
        const tilt = Math.max(-13, Math.min(13, bvx * 1.3))
        const squash = Math.min(0.1, Math.abs(bvy) * 0.008)
        const bob = Math.sin(time / 520) * 5
        buddy.style.transform = `translate(${bx}px, ${by + bob}px) rotate(${tilt}deg) scale(${1 + squash}, ${1 - squash})`
      }
      raf = window.requestAnimationFrame(tick)
    }
    raf = window.requestAnimationFrame(tick)
    cleanups.push(() => window.cancelAnimationFrame(raf))

    return () => {
      cleanups.forEach((fn) => fn())
      timeouts.forEach((t) => clearTimeout(t))
      page.classList.remove('landing-motion-on', 'landing-buddy-on')
    }
  }, [pageRef])

  return (
    <>
      <div ref={dotRef} className="landing-cursor-dot" aria-hidden="true" />
      <div ref={ringRef} className="landing-cursor-ring" aria-hidden="true" />
      <div ref={buddyRef} className="landing-buddy" aria-hidden="true">
        <span ref={bubbleRef} className="landing-buddy__bubble" />
        <img src={bomiRobotUrl} alt="" draggable={false} />
      </div>
    </>
  )
}
