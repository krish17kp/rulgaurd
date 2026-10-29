import { useRef, useState } from 'react'
import { motion, useMotionValueEvent, useScroll, useTransform } from 'motion/react'
import { STAGE, data, hours } from '../data'
import { Bearing } from './Visuals'

const RUN = data.bearings.Bearing2_2
const N = RUN.hi.length
const W = 600
const H = 260
const pts = RUN.hi.map((v, i) => [(i / (N - 1)) * W, H - 20 - Math.min(1, Math.max(0, v)) * (H - 40)])
const PATH = 'M' + pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' L')

/** Sticky scroll scene: scrolling plays one real bearing's life from first spin to failure. */
export function Story() {
  const ref = useRef<HTMLDivElement>(null)
  const { scrollYProgress } = useScroll({ target: ref, offset: ['start start', 'end end'] })
  const draw = useTransform(scrollYProgress, [0.02, 0.95], [0, 1])
  const [i, setI] = useState(0)
  useMotionValueEvent(draw, 'change', (v) => setI(Math.round(Math.min(1, Math.max(0, v)) * (N - 1))))

  const stage = STAGE[RUN.stage[i]]
  const [cx, cy] = pts[i]

  return (
    <section id="story" ref={ref} className="relative h-[320vh]">
      <div className="sticky top-0 flex h-svh items-center overflow-hidden">
        <motion.div
          className="absolute inset-0 -z-10"
          animate={{ backgroundColor: stage.hex }}
          transition={{ duration: 0.6 }}
          aria-hidden
        />
        <div className="mx-auto grid w-full max-w-6xl items-center gap-5 pt-16 px-4 sm:gap-8 sm:pt-0 sm:px-6 lg:grid-cols-[0.8fr_1.2fr]">
          <div>
            <p className="font-display text-sm font-bold">One bearing, start to finish</p>
            <motion.h2
              key={stage.label}
              initial={{ y: 30, opacity: 0, rotate: -2 }}
              animate={{ y: 0, opacity: 1, rotate: 0 }}
              className="mt-3 font-display text-[clamp(2.4rem,6vw,4.6rem)] leading-none font-extrabold tracking-tight"
            >
              {stage.label}.
            </motion.h2>
            <p className="mt-2 max-w-sm sm:mt-4 sm:text-lg">{stage.line}</p>
            <div className="mt-4 flex items-center gap-5 sm:mt-8">
              <Bearing color={stage.hex} wear={i / (N - 1)} className="w-16 sm:w-24" />
              <div className="font-display tabular-nums">
                <p className="text-sm">Health indicator</p>
                <p className="text-3xl font-extrabold sm:text-4xl">{RUN.hi[i].toFixed(2)}</p>
                <p className="text-sm">{hours(RUN.actual[i])}h of life left</p>
              </div>
            </div>
          </div>

          <div className="rounded-[2rem] border-[3px] border-ink bg-paper p-4 shadow-[8px_8px_0_0_var(--color-ink)] sm:p-6">
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Health indicator of FEMTO Bearing 2_2 falling from 1 to 0 over its life">
              {[0.25, 0.5, 0.75].map((f) => (
                <line key={f} x1="0" x2={W} y1={H * f} y2={H * f} stroke="var(--color-ink)" strokeOpacity="0.12" strokeDasharray="4 6" />
              ))}
              <path d={PATH} fill="none" stroke="var(--color-ink)" strokeOpacity="0.12" strokeWidth="4" />
              <motion.path d={PATH} fill="none" stroke="var(--color-cobalt)" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round" style={{ pathLength: draw }} />
              <circle cx={cx} cy={cy} r="11" fill={stage.hex} stroke="var(--color-ink)" strokeWidth="4" />
            </svg>
            <div className="mt-2 flex justify-between text-xs text-ink-soft">
              <span>first spin</span>
              <span className="hidden sm:inline">FEMTO Bearing 2_2, real health indicator</span>
              <span>failure</span>
            </div>
          </div>
        </div>
        <p className="absolute bottom-6 left-1/2 hidden sm:block w-[min(92%,40rem)] -translate-x-1/2 text-center text-sm">
          FEMTO bearings stay flat, then fall off a cliff. Warning time across runs ranged from about 4 hours down to 2 minutes.
        </p>
      </div>
    </section>
  )
}
