import { useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Check, FileUp, LoaderCircle, Play, TriangleAlert } from 'lucide-react'
import { STAGE, data, hours } from '../data'
import { Bearing, Wave } from './Visuals'

const RUNS = Object.keys(data.bearings)
const STEPS = ['Reading the recording', 'Extracting 30+ vibration features', 'Checking the model applies', 'Scoring health', 'Estimating life left']
type Phase = { kind: 'idle' } | { kind: 'running'; step: number; file?: string } | { kind: 'done' } | { kind: 'offline'; file: string }

export function Analyzer() {
  const [run, setRun] = useState(RUNS[0])
  const [pct, setPct] = useState(70)
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [drag, setDrag] = useState(false)
  const timers = useRef<number[]>([])

  const r = data.bearings[run]
  const i = Math.round((pct / 100) * (r.hi.length - 1))
  const stage = STAGE[r.stage[i]]

  const go = (file?: string) => {
    timers.current.forEach(clearTimeout)
    const last = file ? 2 : STEPS.length
    timers.current = Array.from({ length: last + 1 }, (_, s) =>
      window.setTimeout(() => {
        if (s < last) setPhase({ kind: 'running', step: s, file })
        else setPhase(file ? { kind: 'offline', file } : { kind: 'done' })
      }, s * 420),
    )
  }

  const onFile = (f?: File | null) => f && go(f.name)

  return (
    <section id="try" className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
      <h2 className="font-display text-[clamp(2rem,5vw,3.6rem)] leading-[1.02] font-extrabold tracking-tight">Run it yourself.</h2>
      <p className="mt-4 max-w-2xl text-lg text-ink-soft">
        Pick a real FEMTO bearing and a moment in its life, or drop in your own recording. Each run uses the model that was not trained on it.
      </p>

      <div className="mt-10 grid gap-6 lg:grid-cols-2">
        <div className="flex flex-col gap-6 rounded-[2rem] border-[3px] border-ink bg-paper-2 p-5 shadow-[var(--shadow-hard)] sm:p-7">
          <fieldset>
            <legend className="font-display text-sm font-bold">Bearing</legend>
            <div className="mt-3 flex flex-wrap gap-2">
              {RUNS.map((b) => (
                <button
                  key={b}
                  type="button"
                  onClick={() => { setRun(b); setPhase({ kind: 'idle' }) }}
                  aria-pressed={b === run}
                  className={`rounded-full border-2 border-ink px-3 py-1.5 text-sm font-semibold transition active:scale-95 ${b === run ? 'bg-cobalt text-paper shadow-[var(--shadow-hard-sm)]' : 'bg-paper hover:bg-mint'}`}
                >
                  {b.replace('Bearing', '')}
                </button>
              ))}
            </div>
          </fieldset>

          <div>
            <label htmlFor="moment" className="font-display text-sm font-bold">How far into its life: {pct}%</label>
            <input id="moment" type="range" min={0} max={100} value={pct} onChange={(e) => { setPct(+e.target.value); setPhase({ kind: 'idle' }) }} className="age-slider mt-3" />
          </div>

          <button
            type="button"
            onClick={() => go()}
            className="flex items-center justify-center gap-2 rounded-full border-2 border-ink bg-ink px-6 py-3.5 font-display text-sm font-bold text-paper shadow-[var(--shadow-hard-sm)] transition hover:bg-cobalt active:translate-y-0.5 active:shadow-none"
          >
            <Play size={16} /> Analyze this moment
          </button>

          <label
            onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); onFile(e.dataTransfer.files[0]) }}
            className={`flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed border-ink p-6 text-center transition ${drag ? 'scale-[1.02] bg-butter' : 'bg-paper hover:bg-paper-2'}`}
          >
            <FileUp />
            <span className="font-semibold">Drop a CSV, ZIP or RAR recording</span>
            <span className="text-sm text-ink-soft">FEMTO, XJTU-SY, IMS, CWRU, Paderborn or a mapped custom format</span>
            <input type="file" accept=".csv,.zip,.rar,.txt,.mat" className="sr-only" onChange={(e) => onFile(e.target.files?.[0])} />
          </label>
        </div>

        <div className="relative min-h-[26rem] overflow-hidden rounded-[2rem] border-[3px] border-ink bg-ink p-5 text-paper shadow-[var(--shadow-hard)] sm:p-7" aria-live="polite">
          <AnimatePresence mode="wait">
            {phase.kind === 'idle' && (
              <motion.div key="idle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex h-full flex-col justify-between gap-6">
                <p className="font-display text-xl font-bold">Ready when you are.</p>
                <div className="h-28 overflow-hidden rounded-2xl border-2 border-paper/30">
                  <Wave wear={i / (r.hi.length - 1)} color={stage.hex} className="h-full w-full" />
                </div>
                <p className="text-sm text-paper/70">Live preview of the signal at {pct}% of {run.replace('Bearing', 'Bearing ')}'s life.</p>
              </motion.div>
            )}

            {phase.kind === 'running' && (
              <motion.ol key="run" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="space-y-3">
                {phase.file && <p className="mb-4 truncate font-display text-sm font-bold">{phase.file}</p>}
                {STEPS.map((s, k) => (
                  <motion.li key={s} initial={{ x: -12, opacity: 0 }} animate={{ x: 0, opacity: k <= phase.step ? 1 : 0.3 }} className="flex items-center gap-3">
                    {k < phase.step ? <Check className="text-mint" size={20} /> : k === phase.step ? <LoaderCircle className="animate-spin text-butter" size={20} /> : <span className="size-5 rounded-full border-2 border-paper/30" />}
                    {s}
                  </motion.li>
                ))}
              </motion.ol>
            )}

            {phase.kind === 'done' && (
              <motion.div key="done" initial={{ opacity: 0, scale: 0.94 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }} transition={{ type: 'spring', stiffness: 200, damping: 18 }}>
                <div className="flex items-center gap-4">
                  <Bearing color={stage.hex} wear={i / (r.hi.length - 1)} className="w-24 shrink-0" />
                  <div>
                    <span className="inline-block -rotate-3 rounded-full border-2 border-paper px-3 py-1 font-display text-xs font-bold text-ink" style={{ background: stage.hex }}>{stage.label}</span>
                    <p className="mt-2 text-sm text-paper/70">{stage.line}</p>
                  </div>
                </div>
                <dl className="mt-6 grid grid-cols-2 gap-3">
                  {[
                    ['Predicted life left', `${hours(r.pred[i])}h`],
                    ['Actually left', `${hours(r.actual[i])}h`],
                    ['Health indicator', r.hi[i].toFixed(2)],
                    ['Applicability', 'High'],
                  ].map(([k, v], n) => (
                    <motion.div key={k} initial={{ y: 14, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.1 + n * 0.07 }} className="rounded-2xl border-2 border-paper/25 p-4">
                      <dt className="text-xs text-paper/60">{k}</dt>
                      <dd className="mt-1 font-display text-2xl font-extrabold tabular-nums">{v}</dd>
                    </motion.div>
                  ))}
                </dl>
                <p className="mt-5 text-xs text-paper/60">The explanation layer only describes these numbers. It never changes them.</p>
              </motion.div>
            )}

            {phase.kind === 'offline' && (
              <motion.div key="off" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex flex-col gap-4">
                <TriangleAlert className="text-butter" size={32} />
                <p className="font-display text-xl font-bold">The analysis server isn't connected yet.</p>
                <p className="text-paper/75">
                  <span className="font-semibold text-paper">{phase.file}</span> was read in your browser, but scoring happens on the server.
                  This local preview runs without it. Once the site is deployed, the same upload goes through the full pipeline.
                </p>
                <button type="button" onClick={() => go()} className="w-fit rounded-full border-2 border-paper bg-mint px-5 py-2.5 font-display text-sm font-bold text-ink">
                  Analyze a sample bearing instead
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </section>
  )
}
