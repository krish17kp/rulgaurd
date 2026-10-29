import { useRef, useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { Check, FileUp, LoaderCircle, Play, TriangleAlert } from 'lucide-react'
import { STAGE, data, hours } from '../data'
import { Bearing, Wave } from './Visuals'
import { BorderBeam } from './ui/border-beam'
import confetti from 'canvas-confetti'
import { prefersReducedMotion } from '../data'

const RUNS = Object.keys(data.bearings)
const STEPS = ['Reading the recording', 'Extracting 30+ vibration features', 'Checking the model applies', 'Scoring health', 'Estimating life left']
type Result = { ok: boolean; chip?: string; lines: string[] }
type Phase = { kind: 'idle' } | { kind: 'running'; step: number; file?: string } | { kind: 'done' } | { kind: 'inspected'; file: string; result: Result }

// The full app and the lab live on this same domain (deploy/nginx/rulguard.conf); env overrides are for local dev.

// Matches the API's MAX_UPLOAD_BYTES and nginx client_max_body_size; anything bigger never reaches the server.
const MAX_UPLOAD_BYTES = 64 * 1024 * 1024
const mb = (n: number) => `${(n / 1024 / 1024).toFixed(n < 10 * 1024 * 1024 ? 1 : 0)} MB`
type Json = Record<string, any>

/** Files a browser upload can never analyze: answered locally, with what to do instead. */
function precheck(f: File): Result | null {
  const part = f.name.match(/\.part0*(\d+)\.rar$/i)
  if (part)
    return { ok: false, chip: `archive part ${part[1]}`, lines: [
      `This is one piece of a multi-part RAR archive (${mb(f.size)}). A single part can't be opened on its own, so there is nothing to analyze yet.`,
      /xjtu/i.test(f.name)
        ? 'The full XJTU-SY run-to-failure analysis, including which bearings get an RUL estimate and why the rest are withheld, was run offline and lives in the research lab. Single recordings can be analyzed right here or in the RULGuard app.'
        : 'Whole archives are analyzed in the research lab, where all parts are read together.',
    ] }
  if (/\.(rar|7z)$/i.test(f.name))
    return { ok: false, chip: 'archive', lines: [`RAR and 7z archives (${mb(f.size)}) are extracted and analyzed in the research lab, not in this quick check.`] }
  // Headerless files from datasets the pipeline reads with its own adapters (ims.py, femto.py, college.py).
  if (/^\d{4}(\.\d{2}){5}$/.test(f.name))
    return { ok: false, chip: 'IMS snapshot', lines: [
      'This is one IMS snapshot: 1 s of headerless vibration at 20 kHz. IMS has no elapsed-time label inside a single file, so its run-to-failure tests are analyzed as whole folders in the research lab (Cross-Dataset Validation).',
    ] }
  if (/^temp_\d+\.csv$/i.test(f.name))
    return { ok: false, chip: 'FEMTO temperature', lines: [
      'This is a FEMTO temperature file. Life is predicted from the vibration files next to it: drop the matching acc_NNNNN.csv instead.',
    ] }
  if (/^logfile_.*\.csv$/i.test(f.name))
    return { ok: false, chip: 'college rig log', lines: [
      `This looks like a college test-rig log (${mb(f.size)}). These hour-long headerless logs are read by the college adapter in the offline pipeline, and their results are on the research lab's Health Indicator and RUL pages.`,
    ] }
  if (f.size > MAX_UPLOAD_BYTES)
    return { ok: false, chip: 'too large', lines: [`${mb(f.size)} is over the ${mb(MAX_UPLOAD_BYTES)} quick-check limit. Drop a single recording here, or analyze the full dataset in the research lab.`] }
  return null
}

const errorText = (status: number, j: Json | null) =>
  status === 413 ? `The file is over the ${mb(MAX_UPLOAD_BYTES)} upload limit.`
    : (j?.message ?? (typeof j?.detail === 'string' ? j.detail : `The analysis server returned an error (${status}).`))

/** Each file type goes to the endpoint built for it; the card shows the real response. */
async function analyzeUpload(f: File): Promise<Result> {
  const name = f.name.toLowerCase()
  const path = name.endsWith('.zip') ? '/api/analyze/femto-bearing-zip'
    : name.endsWith('.mat') ? '/api/analyze/mat'
      : /^acc_\d+\.csv$/.test(name) ? '/api/predict/rul/femto-acquisition'
        : '/api/dataset/inspect'
  const form = new FormData()
  form.append('file', f)
  // XJTU-SY recordings carry named columns but no rate; 25.6 kHz is fixed by the dataset (xjtu.py XJTU_SAMPLE_RATE_HZ).
  const xjtu = path.endsWith('inspect') && (await f.slice(0, 200).text()).startsWith('Horizontal_vibration_signals')
  if (xjtu) form.append('declared_sampling_rate_hz', '25600')
  const res = await fetch(path, { method: 'POST', body: form })
  const j: Json | null = await res.json().catch(() => null)
  if (!res.ok || !j) return { ok: false, lines: [errorText(res.status, j)] }
  if (path.endsWith('femto-bearing-zip')) {
    const n = j.stage.length - 1
    const counts = (['HEALTHY', 'DEGRADING', 'CRITICAL'] as const).map((k) => `${j.stage.filter((x: string) => x === k).length} ${k.toLowerCase()}`)
    return { ok: true, chip: j.bearing_run_id, lines: [
      `${j.acquisition_count} acquisitions at ${j.sample_rate_hz} Hz. Final stage: ${j.stage[n]}, health indicator ${j.reference_hi[n].toFixed(2)}.`,
      `Stages across the run: ${counts.join(', ')}.`,
      j.held_out_mae_seconds != null ? `Held-out RUL error over the run: ${hours(j.held_out_mae_seconds)}h on average.` : (j.held_out_unavailable_reason ?? ''),
    ].filter(Boolean) }
  }
  if (path.endsWith('mat'))
    return { ok: true, chip: j.dataset_label, lines: [
      `${j.n_samples} samples at ${j.sample_rate_hz} Hz, channel ${j.channel}. Model applicability: ${j.applicability_level}.`,
      j.rul_supported ? `Predicted life left: ${hours(j.rul_seconds)}h.` : `RUL withheld: ${j.note}`,
    ] }
  if (path.endsWith('femto-acquisition'))
    return { ok: true, chip: `${j.applicability_level ?? ''} applicability`.trim(), lines: [
      `Predicted life left: ${hours(j.rul_seconds)}h (${j.rul_seconds} s), model ${j.model_name}.`,
      ...(j.applicability_reasons ?? []).slice(0, 2),
    ] }
  // The API's adapter guidance is written for developers; visitors get the fix in plain words.
  if (j.compatibility === 'ADAPTER_REQUIRED') {
    const missing: string[] = j.required_action?.missing ?? []
    const rate = missing.some((m) => m.startsWith('declared_sampling_rate_hz'))
    const what = rate && missing.includes('declared_units') ? 'sampling rate and units' : rate ? 'sampling rate' : 'units'
    return { ok: false, chip: xjtu ? 'XJTU-SY recording' : 'needs more info', lines: [
      (j.reasons ?? []).some((r: string) => r.startsWith('no header row'))
        ? 'This CSV has no header row, so its columns cannot be identified. Add a header such as time,vibration_x,vibration_y and drop it again.'
        : `${xjtu ? 'Recognized as an XJTU-SY recording at the dataset\'s documented 25.6 kHz.' : 'The vibration columns were found.'} The ${what} must be declared, because RULGuard never guesses them. Declare them on the upload page of the RULGuard app${rate ? ', or add a time column in seconds' : ''}.`,
    ] }
  }
  return { ok: true, chip: j.compatibility?.replaceAll('_', ' ').toLowerCase(), lines: [j.required_action?.message, ...(j.reasons ?? []).slice(0, 2)].filter(Boolean) }
}

export function Analyzer() {
  const [run, setRun] = useState(RUNS[0])
  const [pct, setPct] = useState(70)
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' })
  const [drag, setDrag] = useState(false)
  const timers = useRef<number[]>([])

  const r = data.bearings[run]
  const i = Math.round((pct / 100) * (r.hi.length - 1))
  const stage = STAGE[r.stage[i]]

  const go = () => {
    timers.current.forEach(clearTimeout)
    const last = STEPS.length
    timers.current = Array.from({ length: last + 1 }, (_, s) =>
      window.setTimeout(() => {
        if (s < last) setPhase({ kind: 'running', step: s })
        else {
          setPhase({ kind: 'done' })
          if (!prefersReducedMotion())
            confetti({ particleCount: 90, spread: 75, origin: { x: 0.75, y: 0.6 }, colors: ['#3d2bff', '#ff4fd8', '#38f2b1', '#ffe14d'] })
        }
      }, s * 420),
    )
  }

  const onFile = async (f?: File | null) => {
    if (!f) return
    timers.current.forEach(clearTimeout)
    const early = precheck(f)
    if (early) return setPhase({ kind: 'inspected', file: f.name, result: early })
    setPhase({ kind: 'running', step: 0, file: f.name })
    let result: Result
    try {
      result = await analyzeUpload(f)
    } catch {
      result = { ok: false, lines: ['Could not reach the analysis server. Check your connection and try again.'] }
    }
    setPhase({ kind: 'inspected', file: f.name, result })
  }

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
            <span className="font-semibold">Drop a CSV, .mat or bearing ZIP (up to 64 MB)</span>
            <span className="text-sm text-ink-soft">FEMTO acquisitions and bearing ZIPs, CWRU/Paderborn .mat, or any headered vibration CSV. Large RAR datasets go to the research lab.</span>
            <input type="file" accept=".csv,.zip,.rar,.txt,.mat" className="sr-only" onChange={(e) => onFile(e.target.files?.[0])} />
          </label>
        </div>

        <div className="relative min-h-[26rem] overflow-hidden rounded-[2rem] border-[3px] border-ink bg-ink p-5 text-paper shadow-[var(--shadow-hard)] sm:p-7" aria-live="polite">
          {phase.kind !== 'idle' && <BorderBeam size={160} duration={5} colorFrom="#38f2b1" colorTo="#ffe14d" borderWidth={3} />}
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

            {phase.kind === 'inspected' && (
              <motion.div key="insp" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex flex-col gap-4">
                <p className="truncate font-display text-sm font-bold">{phase.file}</p>
                {!phase.result.ok && <TriangleAlert className="text-butter" size={28} />}
                {phase.result.chip && (
                  <span className={`w-fit -rotate-2 rounded-full border-2 border-paper px-3 py-1 font-display text-xs font-bold text-ink ${phase.result.ok ? 'bg-mint' : 'bg-butter'}`}>
                    {phase.result.chip}
                  </span>
                )}
                {phase.result.lines.map((l) => <p key={l} className="text-paper/85">{l}</p>)}
                <div className="flex flex-wrap gap-3">
                  <a href="/upload" className="rounded-full border-2 border-paper bg-mint px-5 py-2.5 font-display text-sm font-bold text-ink">Run the full analysis</a>
                  <a href="/results" className="rounded-full border-2 border-paper px-5 py-2.5 font-display text-sm font-bold">See full dataset results</a>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </section>
  )
}
