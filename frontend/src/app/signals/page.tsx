"use client";

import { useEffect, useState } from "react";
import { ApiError, FemtoSignalResponse } from "@/lib/api";
import { SignalSource, getFemtoSignal, getSnapshotSignal, listSignals } from "@/lib/labApi";
import { SignalView } from "@/components/SignalAndFeatures";

type Loaded = { data: FemtoSignalResponse; source: string };

/** Signal & FFT and the raw FEMTO explorer from the research lab: browse every FEMTO learning
 * acquisition stored on the server, or the measured college windows bundled with the site. */
export default function SignalsPage() {
  const [sources, setSources] = useState<SignalSource[] | null>(null);
  const [selected, setSelected] = useState(0);
  const [index, setIndex] = useState(1);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSignals()
      .then((list) => {
        setSources(list);
        if (list[0]?.source === "femto_raw") setIndex(Math.ceil(list[0].acquisition_count / 2));
      })
      .catch((err) => setError((err as ApiError).detail ?? String(err)));
  }, []);

  const current = sources?.[selected];

  function pick(i: number) {
    setSelected(i);
    setLoaded(null);
    const s = sources![i];
    setIndex(s.source === "femto_raw" ? Math.ceil(s.acquisition_count / 2) : s.sequence_indices[0]);
  }

  async function show() {
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      if (current.source === "femto_raw") {
        const bearing = current.bearing_run_id.replace("femto:", "");
        const data = await getFemtoSignal(bearing, index);
        setLoaded({ data, source: `${bearing} acquisition ${index} of ${current.acquisition_count}, read from the server's FEMTO files` });
      } else {
        const data = await getSnapshotSignal(current.bearing_run_id, index);
        setLoaded({ data, source: `${current.bearing_run_id} window #${index}, bundled with the site` });
      }
    } catch (err) {
      setError((err as ApiError).detail ?? String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-16">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Signals &amp; FFT</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Look at any real recording: its vibration waveform, frequency spectrum and the features the
          model reads. Every FEMTO learning acquisition is stored on the server; college data ships as
          a few measured windows.
        </p>
      </header>

      {error && <p className="text-sm text-danger">{error}</p>}
      {!sources && !error && <p className="text-sm text-foreground-muted">Loading recordings…</p>}

      {sources && (
        <section className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface p-4">
          <label className="flex flex-col gap-1 text-sm font-medium">
            Bearing
            <select
              value={selected}
              onChange={(e) => pick(Number(e.target.value))}
              className="rounded-lg border border-surface-border bg-background px-3 py-2"
            >
              {sources.map((s, i) => (
                <option key={s.bearing_run_id} value={i}>
                  {s.label}
                </option>
              ))}
            </select>
          </label>

          {current?.source === "femto_raw" ? (
            <label className="flex flex-col gap-1 text-sm font-medium">
              Acquisition {index} of {current.acquisition_count} (one every 10 s, 0.1 s long)
              <input
                type="range"
                min={1}
                max={current.acquisition_count}
                value={index}
                onChange={(e) => setIndex(Number(e.target.value))}
              />
            </label>
          ) : (
            current && (
              <label className="flex flex-col gap-1 text-sm font-medium">
                Window
                <select
                  value={index}
                  onChange={(e) => setIndex(Number(e.target.value))}
                  className="rounded-lg border border-surface-border bg-background px-3 py-2"
                >
                  {current.sequence_indices.map((s, i) => (
                    <option key={s} value={s}>
                      #{s} ({["early life", "mid-life", "late life"][i] ?? "window"})
                    </option>
                  ))}
                </select>
              </label>
            )
          )}

          <button
            type="button"
            onClick={() => void show()}
            disabled={busy}
            className="self-start rounded-full border-2 border-surface-border bg-mint px-5 py-2 font-display text-sm font-bold disabled:opacity-60"
          >
            {busy ? "Loading…" : "Show recording"}
          </button>
        </section>
      )}

      {loaded && <SignalView data={loaded.data} source={loaded.source} />}
    </main>
  );
}
