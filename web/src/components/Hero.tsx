import { useEffect, useState } from 'react'
import { animate, motion } from 'motion/react'
import { Sparkles } from 'lucide-react'
import { Bearing, KineticTitle, Sticker, Wave } from './Visuals'
import Magnet from './Magnet'
import ShinyText from './ShinyText'
import { BorderBeam } from './ui/border-beam'
import { InteractiveGridPattern } from './ui/interactive-grid-pattern'
import { STAGE, data, hours, prefersReducedMotion } from '../data'

const RUN = data.bearings.Bearing3_2
const LAST = RUN.hi.length - 1

export function Hero() {
  const [i, setI] = useState(0)

  // One-time intro: the bearing ages a little on its own so the slider reads as alive.
  useEffect(() => {
    if (prefersReducedMotion()) return setI(Math.round(LAST * 0.3))
    const c = animate(0, LAST * 0.42, { duration: 2.4, delay: 1, ease: 'easeInOut', onUpdate: (v) => setI(Math.round(v)) })
    return () => c.stop()
  }, [])

  const stage = STAGE[RUN.stage[i]]
  const wear = i / LAST

  return (
    <section id="top" className="relative isolate mx-auto grid max-w-6xl gap-10 px-4 pt-32 pb-16 sm:px-6 lg:grid-cols-[1.15fr_0.85fr] lg:items-center lg:pt-36">
      <InteractiveGridPattern
        width={56}
        height={56}
        squares={[40, 16]}
        className="-z-10 !border-0 [mask-image:radial-gradient(ellipse_at_30%_40%,black,transparent_70%)] opacity-60"
        squaresClassName="stroke-ink/10 fill-transparent hover:fill-mint transition-colors duration-300"
      />
      <div className="relative z-10">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="mb-6 flex flex-wrap gap-2">
          <Sticker bg="var(--color-butter)"><Sparkles size={14} /> <ShinyText text="Capstone research project" color="#14123a" shineColor="#ffffff" speed={2.5} /></Sticker>
          <Sticker bg="var(--color-paper)">Built over 6 months</Sticker>
        </motion.div>

        <KineticTitle
          lines={['Bearings vibrate', 'before they die.']}
          className="font-display text-[clamp(2.6rem,7.4vw,5.6rem)] leading-[0.95] font-extrabold tracking-[-0.03em]"
        />

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.9 }}
          className="mt-6 max-w-[34rem] text-lg leading-relaxed text-ink-soft"
        >
          RULGuard listens to that vibration and estimates how many hours a bearing has left. When your data doesn't look like what it
          learned from, it tells you instead of guessing.
        </motion.p>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 1.05 }} className="mt-8 flex flex-wrap gap-3">
          <Magnet padding={50} magnetStrength={2.5}>
          <a href="#try" className="rounded-full border-2 border-ink bg-cobalt px-6 py-3 font-display text-sm font-bold text-paper shadow-[var(--shadow-hard)] transition hover:-translate-y-0.5 hover:shadow-[7px_7px_0_0_var(--color-ink)] active:translate-y-0.5 active:shadow-none">
              Try it on a real bearing
            </a>
          </Magnet>
          <Magnet padding={50} magnetStrength={2.5}>
          <a href="#results" className="rounded-full border-2 border-ink bg-paper px-6 py-3 font-display text-sm font-bold shadow-[var(--shadow-hard)] transition hover:-translate-y-0.5 hover:bg-mint active:translate-y-0.5 active:shadow-none">
              See the results
            </a>
          </Magnet>
        </motion.div>
      </div>

      {/* the interactive bearing card */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9, rotate: -3 }}
        animate={{ opacity: 1, scale: 1, rotate: 0 }}
        transition={{ delay: 0.4, type: 'spring', stiffness: 120, damping: 16 }}
        className="relative rounded-[2rem] border-[3px] border-ink bg-paper-2 p-5 shadow-[8px_8px_0_0_var(--color-ink)] sm:p-6"
      >
        <div className="flex items-start gap-4">
          <Bearing color={stage.hex} wear={wear} className="w-32 shrink-0 sm:w-40" />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-ink-soft">Life left, predicted</p>
            <p className="font-display text-5xl font-extrabold tabular-nums sm:text-6xl">
              {hours(RUN.pred[i])}
              <span className="text-2xl">h</span>
            </p>
            <p className="mt-1 text-sm text-ink-soft tabular-nums">Actually left: {hours(RUN.actual[i])}h</p>
            <motion.span
              key={stage.label}
              initial={{ scale: 0.6, rotate: -8 }}
              animate={{ scale: 1, rotate: -3 }}
              className="mt-3 inline-block rounded-full border-2 border-ink px-3 py-1 font-display text-xs font-bold"
              style={{ background: stage.hex }}
            >
              {stage.label}
            </motion.span>
          </div>
        </div>

        <div className="mt-4 h-20 overflow-hidden rounded-2xl border-2 border-ink bg-ink">
          <Wave wear={wear} color={stage.hex} className="h-full w-full" />
        </div>

        <BorderBeam size={120} duration={7} colorFrom="#ff4fd8" colorTo="#3d2bff" borderWidth={3} />
        <label htmlFor="age" className="mt-5 block font-display text-sm font-bold">
          Drag to age the bearing
        </label>
        <input
          id="age"
          type="range"
          min={0}
          max={LAST}
          value={i}
          onChange={(e) => setI(+e.target.value)}
          className="age-slider mt-3"
          aria-valuetext={`${stage.label}, ${hours(RUN.pred[i])} hours predicted`}
        />
        <p className="mt-3 text-xs text-ink-soft">
          Real FEMTO test run (Bearing 3_2), predicted by a model that never saw this bearing.
        </p>
      </motion.div>
    </section>
  )
}
