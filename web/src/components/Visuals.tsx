import { useEffect, useRef, type ReactNode } from 'react'
import { motion } from 'motion/react'
import { prefersReducedMotion } from '../data'

const BALLS = Array.from({ length: 9 }, (_, i) => {
  const a = (i / 9) * Math.PI * 2
  return [100 + Math.cos(a) * 62, 100 + Math.sin(a) * 62]
})

/** Cross-section of a ball bearing. Balls spin; it starts shaking once wear is high. */
export function Bearing({ color, wear, className }: { color: string; wear: number; className?: string }) {
  const shake = wear > 0.75 && !prefersReducedMotion()
  return (
    <motion.svg
      viewBox="0 0 200 200"
      className={className}
      aria-hidden
      animate={shake ? { x: [0, -3, 3, -2, 2, 0], rotate: [0, -1, 1, 0] } : { x: 0, rotate: 0 }}
      transition={shake ? { duration: 0.35, repeat: Infinity } : { duration: 0.2 }}
    >
      <circle cx="100" cy="100" r="95" fill="var(--color-paper)" stroke="var(--color-ink)" strokeWidth="5" />
      <circle cx="100" cy="100" r="81" fill="var(--color-cobalt)" stroke="var(--color-ink)" strokeWidth="4" />
      <g className="spin-slow">
        <circle cx="100" cy="100" r="62" fill="none" stroke="var(--color-ink)" strokeWidth="2" strokeDasharray="4 6" />
        {BALLS.map(([x, y], i) => (
          <g key={i}>
            <circle cx={x} cy={y} r="14" fill={color} stroke="var(--color-ink)" strokeWidth="4" style={{ transition: 'fill .4s' }} />
            <circle cx={x - 4} cy={y - 4} r="3.5" fill="white" opacity="0.8" />
          </g>
        ))}
      </g>
      <circle cx="100" cy="100" r="44" fill="var(--color-paper)" stroke="var(--color-ink)" strokeWidth="4" />
      <circle cx="100" cy="100" r="24" fill="var(--color-ink)" />
      <circle cx="100" cy="100" r="9" fill={color} style={{ transition: 'fill .4s' }} />
    </motion.svg>
  )
}

/** Live vibration trace. Amplitude, noise and impact spikes all grow with wear (0..1). */
export function Wave({ wear, color, className }: { wear: number; color: string; className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null)
  const live = useRef({ wear, color })
  useEffect(() => {
    live.current = { wear, color }
  })

  useEffect(() => {
    const c = ref.current!
    const ctx = c.getContext('2d')!
    const reduce = prefersReducedMotion()
    let raf = 0
    let t = 0
    const draw = () => {
      const dpr = window.devicePixelRatio || 1
      const w = c.clientWidth
      const h = c.clientHeight
      if (c.width !== Math.round(w * dpr)) {
        c.width = Math.round(w * dpr)
        c.height = Math.round(h * dpr)
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, w, h)
      const k = live.current.wear
      ctx.strokeStyle = live.current.color
      ctx.lineWidth = 2.5
      ctx.lineJoin = 'round'
      ctx.beginPath()
      for (let x = 0; x <= w; x += 2) {
        const p = (x / w) * 38 + t
        let y = Math.sin(p) * 0.4 + Math.sin(p * 2.7) * 0.2
        y += (Math.random() - 0.5) * k * 1.1
        if (Math.random() < k * k * 0.05) y += (Math.random() - 0.5) * k * 3.4
        y *= 0.22 + k * 0.78
        ctx.lineTo(x, h / 2 - y * h * 0.42)
      }
      ctx.stroke()
      t += 0.09
      if (!reduce) raf = requestAnimationFrame(draw)
    }
    draw()
    return () => cancelAnimationFrame(raf)
  }, [])

  return <canvas ref={ref} className={className} aria-hidden />
}

/** Words slide up out of a mask one after another. The page's single load moment. */
export function KineticTitle({ lines, className }: { lines: string[]; className?: string }) {
  const words = lines.map((line, li) => line.split(' ').map((w, wi) => ({ w, key: `${li}-${wi}` })))
  const offsets = words.map((_, li) => words.slice(0, li).reduce((s, l) => s + l.length, 0))
  return (
    <h1 className={className} aria-label={lines.join(' ')}>
      {words.map((line, li) => (
        <span key={li} className="block" aria-hidden>
          {line.map(({ w, key }, wi) => (
            <span key={key} className="inline-block overflow-hidden pb-[0.08em] align-bottom">
              <motion.span
                className="wiggle inline-block"
                initial={{ y: '110%', rotate: 6 }}
                animate={{ y: 0, rotate: 0 }}
                transition={{ delay: 0.15 + (offsets[li] + wi) * 0.07, type: 'spring', stiffness: 260, damping: 22 }}
              >
                {w}&nbsp;
              </motion.span>
            </span>
          ))}
        </span>
      ))}
    </h1>
  )
}

/** Chunky sticker with a hard shadow. */
export function Sticker({ children, bg, className = '' }: { children: ReactNode; bg: string; className?: string }) {
  return (
    <span
      className={`wiggle inline-flex items-center gap-1.5 rounded-full border-2 border-ink px-3 py-1 text-sm font-semibold shadow-[var(--shadow-hard-sm)] ${className}`}
      style={{ background: bg }}
    >
      {children}
    </span>
  )
}
