import { useEffect, useRef, useState } from 'react'
import { animate, motion, useInView } from 'motion/react'
import { data } from '../data'

const { overall, hidden } = data
const LESS = Math.round((1 - overall.extra_trees / overall.naive) * 100)
const BEARINGS = [...new Set(data.lobo.map((r) => r.bearing))]
const MAX = Math.max(...data.lobo.map((r) => r.mae_h))
const mae = (b: string, m: string) => data.lobo.find((r) => r.bearing === b && r.model === m)!.mae_h

function CountUp({ to, suffix = '' }: { to: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true })
  const [v, setV] = useState(0)
  useEffect(() => {
    if (!inView) return
    const c = animate(0, to, { duration: 1.4, ease: 'easeOut', onUpdate: (x) => setV(Math.round(x)) })
    return () => c.stop()
  }, [inView, to])
  return (
    <span ref={ref} className="tabular-nums">
      {v.toLocaleString()}
      {suffix}
    </span>
  )
}

export function Results() {
  return (
    <section id="results" className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
      <h2 className="max-w-3xl font-display text-[clamp(2rem,5vw,3.6rem)] leading-[1.02] font-extrabold tracking-tight">
        <CountUp to={LESS} suffix="%" /> less error than the naive baseline.
      </h2>
      <p className="mt-4 max-w-2xl text-lg text-ink-soft">
        Tested leave-one-bearing-out: train on five FEMTO bearings, predict the sixth, repeat. Across {(7534).toLocaleString()} predictions the
        Extra Trees model was off by {(overall.extra_trees / 3600).toFixed(2)}h on average, against {(overall.naive / 3600).toFixed(2)}h for the
        naive baseline.
      </p>

      <div className="mt-12 grid gap-6 lg:grid-cols-[1.3fr_0.7fr]">
        <div className="rounded-[2rem] border-[3px] border-ink bg-paper-2 p-5 shadow-[var(--shadow-hard)] sm:p-7">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="font-display text-lg font-bold">Average error per held-out bearing</h3>
            <div className="flex gap-4 text-sm">
              <span className="flex items-center gap-1.5"><i className="size-3 rounded-full border-2 border-ink bg-cobalt" />Extra Trees</span>
              <span className="flex items-center gap-1.5"><i className="size-3 rounded-full border-2 border-ink bg-paper" />Naive</span>
            </div>
          </div>
          <div className="mt-6 space-y-4">
            {BEARINGS.map((b, row) => {
              const et = mae(b, 'extra_trees')
              const nv = mae(b, 'naive')
              return (
                <div key={b} className="grid grid-cols-[5.5rem_1fr] items-center gap-3">
                  <span className="font-display text-xs font-bold">{b.replace('Bearing', 'Bearing ')}</span>
                  <div className="space-y-1.5">
                    {[
                      { v: et, cls: 'bg-cobalt text-paper' },
                      { v: nv, cls: 'bg-paper' },
                    ].map(({ v, cls }, k) => (
                      <motion.div
                        key={k}
                        className={`flex h-6 items-center justify-end rounded-full border-2 border-ink pr-2 text-xs font-bold tabular-nums ${cls}`}
                        initial={{ width: '8%' }}
                        whileInView={{ width: `${Math.max(14, (v / MAX) * 100)}%` }}
                        viewport={{ once: true, margin: '-60px' }}
                        transition={{ type: 'spring', stiffness: 70, damping: 16, delay: row * 0.06 + k * 0.05 }}
                      >
                        {v.toFixed(2)}h
                      </motion.div>
                    ))}
                  </div>
                </div>
              )
            })}
          </div>
          <p className="mt-6 text-sm text-ink-soft">Extra Trees wins on 4 of 6 bearings. On Bearing 1_2 and 3_2 the naive guess is slightly better, and we kept that in.</p>
        </div>

        <div className="flex flex-col gap-6">
          <motion.div
            whileHover={{ rotate: -1.5, y: -4 }}
            className="rounded-[2rem] border-[3px] border-ink bg-butter p-6 shadow-[var(--shadow-hard)]"
          >
            <h3 className="font-display text-lg font-bold">The final exam</h3>
            <p className="mt-2 text-sm">{hidden.n} hidden FEMTO bearings, scored once after the model was frozen.</p>
            <p className="mt-4 font-display text-4xl font-extrabold"><CountUp to={hidden.et_mae} />s</p>
            <p className="text-sm">average error, vs {hidden.naive_mae.toLocaleString()}s naive</p>
          </motion.div>
          <motion.div
            whileHover={{ rotate: 1.5, y: -4 }}
            className="rounded-[2rem] border-[3px] border-ink bg-magenta p-6 shadow-[var(--shadow-hard)]"
          >
            <h3 className="font-display text-lg font-bold">Where it still struggles</h3>
            <p className="mt-2 text-sm">
              {hidden.unsafe} of {hidden.n} hidden predictions were too optimistic, saying a bearing had more life than it did. That's the unsafe direction, so
              we report it up front.
            </p>
          </motion.div>
        </div>
      </div>
    </section>
  )
}
