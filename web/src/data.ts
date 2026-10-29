// Real RULGuard numbers, downsampled by scripts/build_data.py from the repo's metrics files.
import raw from './data.json'

export type Stage = 'HEALTHY' | 'DEGRADING' | 'CRITICAL'
export type Run = { hi: number[]; stage: Stage[]; actual: number[]; pred: number[] }

export const data = raw as unknown as {
  lobo: { bearing: string; model: 'naive' | 'extra_trees'; mae_h: number }[]
  overall: { extra_trees: number; naive: number }
  hidden: { et_mae: number; naive_mae: number; et_phm: number; naive_phm: number; n: number; unsafe: number }
  bearings: Record<string, Run>
}

export const STAGE: Record<Stage, { label: string; hex: string; line: string }> = {
  HEALTHY: { label: 'Healthy', hex: '#38f2b1', line: 'Smooth hum. Nothing to do yet.' },
  DEGRADING: { label: 'Degrading', hex: '#ffe14d', line: 'Small impacts in the signal. Plan the swap.' },
  CRITICAL: { label: 'Critical', hex: '#ff4fd8', line: 'Vibration is spiking. Replace it now.' },
}

export const hours = (s: number) => (Math.max(0, s) / 3600).toFixed(1)

export const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
