import { useEffect, useRef } from 'react'

interface Dot {
  x: number
  y: number
  vx: number
  vy: number
  r: number
}

/**
 * 어두운 절 배경의 입자 흐름. 분홍 점들이 천천히 떠다니다 가까워지면 실처럼 이어진다.
 * 섹션이 화면에 있을 때만 그리고(IntersectionObserver), 모션 축소 환경에서는 아예 그리지
 * 않는다. 부모(.landing-human)가 isolation 컨텍스트라 z-index:-1 로 콘텐츠 뒤에 깔린다.
 */
export function LandingDust() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const host = canvas.parentElement
    if (!host) return
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let dots: Dot[] = []
    let width = 0
    let height = 0
    let raf = 0
    let running = false

    const seed = () => {
      const rect = host.getBoundingClientRect()
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      width = rect.width
      height = rect.height
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      const count = Math.round(Math.min(60, Math.max(28, width / 26)))
      dots = Array.from({ length: count }, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.3,
        r: 0.8 + Math.random() * 1.8,
      }))
    }

    const LINK_DIST_SQ = 90 * 90
    const tick = () => {
      ctx.clearRect(0, 0, width, height)
      for (const d of dots) {
        d.x += d.vx
        d.y += d.vy
        if (d.x < 0) d.x = width
        if (d.x > width) d.x = 0
        if (d.y < 0) d.y = height
        if (d.y > height) d.y = 0
        ctx.beginPath()
        ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2)
        ctx.fillStyle = 'rgba(255, 150, 190, 0.5)'
        ctx.fill()
      }
      for (let i = 0; i < dots.length; i += 1) {
        for (let j = i + 1; j < dots.length; j += 1) {
          const a = dots[i]
          const b = dots[j]
          const dx = a.x - b.x
          const dy = a.y - b.y
          const d2 = dx * dx + dy * dy
          if (d2 < LINK_DIST_SQ) {
            ctx.strokeStyle = `rgba(255, 140, 185, ${0.15 * (1 - d2 / LINK_DIST_SQ)})`
            ctx.beginPath()
            ctx.moveTo(a.x, a.y)
            ctx.lineTo(b.x, b.y)
            ctx.stroke()
          }
        }
      }
      if (running) raf = window.requestAnimationFrame(tick)
    }

    const io = new IntersectionObserver(
      ([entry]) => {
        const next = entry.isIntersecting
        if (next && !running) {
          running = true
          raf = window.requestAnimationFrame(tick)
        } else if (!next) {
          running = false
          window.cancelAnimationFrame(raf)
        }
      },
      { threshold: 0.08 },
    )
    io.observe(canvas)

    const ro = new ResizeObserver(seed)
    ro.observe(host)
    seed()

    return () => {
      io.disconnect()
      ro.disconnect()
      window.cancelAnimationFrame(raf)
    }
  }, [])

  return <canvas ref={canvasRef} className="landing-dust" aria-hidden="true" />
}
