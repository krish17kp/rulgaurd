import { useEffect, useState } from 'react'
import Lenis from 'lenis'
import { AnimatePresence, motion, useScroll, useSpring } from 'motion/react'
import { Menu, X } from 'lucide-react'
import { Hero } from './components/Hero'
import { Story } from './components/Story'
import { Results } from './components/Results'
import { Analyzer } from './components/Analyzer'
import { Sticker } from './components/Visuals'
import ClickSpark from './components/ClickSpark'
import Magnet from './components/Magnet'
import { ScrollVelocity } from './components/ScrollVelocity'
import SpotlightCard from './components/SpotlightCard'
import { prefersReducedMotion } from './data'

const LINKS = [
  ['#how', 'How it works'],
  ['#results', 'Results'],
  ['#try', 'Try it'],
  ['#datasets', 'Datasets'],
  // Same-domain pages: the full analysis app and the Streamlit research lab.
  ['/upload', 'Analyze'],
  ['/lab/', 'Lab'],
]

const TICKER = ['FEMTO PRONOSTIA', 'XJTU-SY', 'IMS NASA', 'CWRU', 'Paderborn', 'NSK 6205 college rig', 'Extra Trees', 'leave-one-bearing-out', 'conformal intervals', 'applicability checks']

const PIPELINE = [
  ['Load', 'Read a raw vibration recording from CSV, ZIP or RAR, whatever the dataset format.', 'var(--color-mint)'],
  ['Featurize', 'Turn every acquisition into 30+ time and frequency features like RMS, kurtosis and spectral entropy.', 'var(--color-butter)'],
  ['Check', 'Compare the signal to the training data. If it looks foreign, RUL is switched off.', 'var(--color-magenta)'],
  ['Score', 'Build a health indicator and band it into healthy, degrading or critical.', 'var(--color-paper)'],
  ['Predict', 'Estimate remaining useful life, with an interval around it.', 'var(--color-cobalt)'],
] as const

const DATASETS = [
  ['FEMTO / PRONOSTIA', 'Trained and tested here. 17 bearings from the IEEE PHM 2012 challenge.', 'Full RUL', 'var(--color-mint)'],
  ['College rig', 'One NSK 6205 bearing, recorded hourly for 128 hours until it failed.', 'Health only', 'var(--color-butter)'],
  ['XJTU-SY', 'Run-to-failure bearings from Xi\'an Jiaotong University.', 'Health only', 'var(--color-butter)'],
  ['IMS (NASA)', 'Multi-week runs on a very different time scale, so the life estimate is switched off.', 'Health only', 'var(--color-butter)'],
  ['CWRU', 'Seeded-fault recordings with no run-to-failure history to learn a lifetime from.', 'Health only', 'var(--color-butter)'],
  ['Paderborn', 'Damaged and healthy bearing recordings from Paderborn University.', 'Health only', 'var(--color-butter)'],
] as const

function Nav() {
  const [open, setOpen] = useState(false)
  const { scrollYProgress } = useScroll()
  const bar = useSpring(scrollYProgress, { stiffness: 120, damping: 24 })
  return (
    <header className="fixed inset-x-0 top-3 z-50 px-3">
      <nav className="relative mx-auto flex max-w-6xl items-center gap-4 overflow-hidden rounded-full border-2 border-ink bg-paper/85 py-2 pr-2 pl-4 shadow-[var(--shadow-hard-sm)] backdrop-blur-md">
        <a href="#top" className="flex items-center gap-2 font-display text-base font-extrabold">
          <img src="/favicon.svg" alt="" className="size-7 spin-slow" />
          RULGuard
        </a>
        <div className="ml-auto hidden items-center gap-1 md:flex">
          {LINKS.map(([href, label]) => (
            <a key={href} href={href} className="rounded-full px-3 py-1.5 text-sm font-semibold transition hover:bg-ink hover:text-paper">
              {label}
            </a>
          ))}
        </div>
        {/* Magnet sets inline display, so the responsive hide lives on this wrapper */}
        <span className="ml-auto hidden sm:block md:ml-0">
        <Magnet padding={40} magnetStrength={3}>
          <a href="#try" className="inline-block rounded-full border-2 border-ink bg-magenta px-4 py-2 font-display text-xs font-bold">
            Analyze a bearing
          </a>
        </Magnet>
        </span>
        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-label={open ? 'Close menu' : 'Open menu'} className="ml-auto rounded-full border-2 border-ink p-2 sm:ml-0 md:hidden">
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
        <motion.span className="absolute inset-x-0 bottom-0 h-[3px] origin-left bg-cobalt" style={{ scaleX: bar }} aria-hidden />
      </nav>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.97 }}
            className="mx-auto mt-2 flex max-w-6xl flex-col rounded-3xl border-2 border-ink bg-paper p-2 shadow-[var(--shadow-hard-sm)] md:hidden"
          >
            {LINKS.map(([href, label]) => (
              <a key={href} href={href} onClick={() => setOpen(false)} className="rounded-2xl px-4 py-3 font-display text-sm font-bold hover:bg-mint">
                {label}
              </a>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  )
}

function Ticker() {
  const sep = <span className="px-6 text-mint">✺</span>
  return (
    <div className="overflow-hidden py-6" aria-hidden>
      <div className="-mx-4 -rotate-2 border-y-[3px] border-ink bg-cobalt py-3 text-paper">
        <ScrollVelocity
          texts={[TICKER.slice(0, 5).join('  ✺  '), TICKER.slice(5).join('  ✺  ')]}
          velocity={60}
          separator={sep}
          className="font-display font-bold"
          fontSize="1.25rem"
          skewWithVelocity={8}
          outlineAlternate
          pauseOnHover
        />
      </div>
    </div>
  )
}

function Pipeline() {
  return (
    <section id="how" className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
      <h2 className="max-w-3xl font-display text-[clamp(2rem,5vw,3.6rem)] leading-[1.02] font-extrabold tracking-tight">From raw vibration to hours left, in five steps.</h2>
      <ol className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {PIPELINE.map(([title, body, bg], i) => (
          <motion.li
            key={title}
            initial={{ y: 40, opacity: 0, rotate: i % 2 ? 3 : -3 }}
            whileInView={{ y: 0, opacity: 1, rotate: i % 2 ? 1 : -1 }}
            whileHover={{ rotate: 0, y: -6 }}
            viewport={{ once: true, margin: '-80px' }}
            transition={{ type: 'spring', stiffness: 140, damping: 16, delay: i * 0.08 }}
            className={`flex flex-col gap-3 rounded-[1.75rem] border-[3px] border-ink p-5 shadow-[var(--shadow-hard)] ${i === 4 ? 'text-paper' : ''}`}
            style={{ background: bg }}
          >
            <span className="grid size-10 place-items-center rounded-full border-2 border-ink bg-paper font-display text-sm font-extrabold text-ink">{i + 1}</span>
            <h3 className="font-display text-xl font-extrabold">{title}</h3>
            <p className="text-sm leading-relaxed">{body}</p>
          </motion.li>
        ))}
      </ol>
    </section>
  )
}

function Datasets() {
  return (
    <section id="datasets" className="bg-ink py-24 text-paper">
      <div className="mx-auto max-w-6xl px-4 sm:px-6">
        <h2 className="max-w-3xl font-display text-[clamp(2rem,5vw,3.6rem)] leading-[1.02] font-extrabold tracking-tight">Six datasets in. One honest answer out.</h2>
        <p className="mt-4 max-w-2xl text-lg text-paper/70">
          Each dataset has its own adapter. The model only gives a life estimate where it was proven to work, and falls back to a health reading everywhere else.
        </p>
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {DATASETS.map(([name, body, verdict, bg], i) => (
            <motion.article
              key={name}
              initial={{ scale: 0.85, opacity: 0, rotate: (i % 3) - 1 }}
              whileInView={{ scale: 1, opacity: 1 }}
              whileHover={{ rotate: i % 2 ? 2 : -2, scale: 1.03 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ type: 'spring', stiffness: 160, damping: 15, delay: (i % 3) * 0.07 }}
              className="h-full"
            >
              <SpotlightCard theme="dark" spotlightColor={bg} className="h-full !rounded-[1.75rem] border-[3px] border-paper/70 !p-6">
              <span className="inline-block rounded-full border-2 border-ink px-3 py-1 font-display text-xs font-bold text-ink" style={{ background: bg }}>
                {verdict}
              </span>
              <h3 className="mt-4 font-display text-xl font-extrabold">{name}</h3>
              <p className="mt-2 text-sm leading-relaxed text-paper/75">{body}</p>
              </SpotlightCard>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  )
}

function Honest() {
  const items = [
    'Life estimates are validated on FEMTO only. Other datasets get a health reading, not a countdown.',
    'Health stages are a severity band. It does not say whether the inner race, outer race or a ball is damaged.',
    'It analyzes recordings after the fact. It is not wired to live sensors.',
    'The language model only explains the numbers and cites sources. It never edits a prediction.',
  ]
  return (
    <section id="limits" className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
      <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
        <h2 className="font-display text-[clamp(2rem,5vw,3.6rem)] leading-[1.02] font-extrabold tracking-tight">What it won't pretend to do.</h2>
        <ul className="space-y-4">
          {items.map((t, i) => (
            <motion.li
              key={t}
              initial={{ x: 40, opacity: 0 }}
              whileInView={{ x: 0, opacity: 1 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.08 }}
              className="flex gap-4 rounded-3xl border-2 border-ink bg-paper-2 p-5 text-lg"
            >
              <span className="mt-1 size-4 shrink-0 rounded-full border-2 border-ink bg-magenta" aria-hidden />
              {t}
            </motion.li>
          ))}
        </ul>
      </div>
    </section>
  )
}

function Footer() {
  return (
    <footer className="overflow-hidden border-t-[3px] border-ink bg-butter pt-16">
      <div className="mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-6 px-4 sm:px-6">
        <div>
          <p className="font-display text-2xl font-extrabold">Built to know when to stay quiet.</p>
          <p className="mt-2 max-w-md text-ink-soft">RULGuard is a capstone research prototype for bearing health monitoring and remaining useful life prediction. Not a safety system.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Sticker bg="var(--color-mint)">Python + scikit-learn</Sticker>
          <Sticker bg="var(--color-paper)">DuckDB + Parquet</Sticker>
          <Sticker bg="var(--color-magenta)">Evidence-grounded RAG</Sticker>
        </div>
      </div>
      <motion.p
        initial={{ y: '40%' }}
        whileInView={{ y: '12%' }}
        viewport={{ once: true }}
        transition={{ type: 'spring', stiffness: 60, damping: 14 }}
        className="mt-10 text-center font-display text-[16.5vw] leading-none font-extrabold tracking-[-0.05em] text-transparent select-none [-webkit-text-stroke:3px_var(--color-ink)]"
        aria-hidden
      >
        RULGuard
      </motion.p>
    </footer>
  )
}

export default function App() {
  useEffect(() => {
    if (prefersReducedMotion()) return
    const lenis = new Lenis({ anchors: { offset: -80 }, autoRaf: true })
    return () => lenis.destroy()
  }, [])

  return (
    <ClickSpark sparkColor={['#3d2bff', '#ff4fd8', '#38f2b1', '#ffe14d']} sparkCount={10} sparkSize={12} sparkRadius={28} shape="star">
      <Nav />
      <main>
        <Hero />
        <Ticker />
        <Pipeline />
        <Story />
        <Results />
        <Analyzer />
        <Datasets />
        <Honest />
      </main>
      <Footer />
    </ClickSpark>
  )
}
