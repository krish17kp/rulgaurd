// Whole datasets (several files, a folder, ZIP/RAR/7Z sets, anything over the quick-check
// limit) go to the server-side dataset jobs the full app uses (/api/jobs, dataset_jobs.py).
// This page only uploads and starts the job; /upload?job=<id> shows its progress and results.

export type Picked = { file: File; name: string }  // name: path relative to the dropped folder

const CHUNK_BYTES = 16 * 1024 * 1024  // same as the app's DatasetJobPanel, under the API's 32 MB chunk limit
const MAX_RETRIES = 5
type Json = Record<string, any>

const clean = (name: string) => name.replace(/\\/g, '/').replace(/^\.\//, '')
const base = (name: string) => clean(name).split('/').pop()!

async function call(path: string, init?: RequestInit): Promise<Json> {
  const res = await fetch(path, init)
  const j: Json | null = await res.json().catch(() => null)
  if (!res.ok) throw Object.assign(new Error(j?.message ?? j?.detail ?? `The server returned an error (${res.status}).`), { status: res.status })
  return j ?? {}
}

/** Every file under the dropped folders/files, with folder-relative names. Entries must be
 * taken from the drop event synchronously, before any await. */
export async function fromEntries(entries: FileSystemEntry[]): Promise<Picked[]> {
  const walk = async (entry: FileSystemEntry, prefix: string): Promise<Picked[]> => {
    if (entry.isFile) {
      const file = await new Promise<File>((ok, err) => (entry as FileSystemFileEntry).file(ok, err))
      return [{ file, name: prefix + entry.name }]
    }
    const reader = (entry as FileSystemDirectoryEntry).createReader()
    const out: Picked[] = []
    for (;;) {  // readEntries returns at most ~100 entries per call
      const batch = await new Promise<FileSystemEntry[]>((ok, err) => reader.readEntries(ok, err))
      if (!batch.length) return out
      for (const e of batch) out.push(...(await walk(e, `${prefix}${entry.name}/`)))
    }
  }
  return (await Promise.all(entries.map((e) => walk(e, '')))).flat()
}

export const fromFileList = (files: FileList): Picked[] =>
  Array.from(files, (file) => ({ file, name: file.webkitRelativePath || file.name }))

/** Create the job, upload every file in resumable chunks, start it; returns the job id. */
export async function sendToJob(picked: Picked[], onProgress: (sent: number, total: number) => void): Promise<string> {
  const files = picked.map((p) => ({ name: clean(p.name), size: p.file.size }))
  const job = await call('/api/jobs', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ files }) })
  const byName = new Map<string, File>()
  picked.forEach((p, i) => { byName.set(files[i].name, p.file); if (!byName.has(base(p.name))) byName.set(base(p.name), p.file) })
  const total = files.reduce((s, f) => s + f.size, 0)
  let sent = 0
  for (const [i, jf] of (job.files as Array<{ name: string; size: number }>).entries()) {
    const file = byName.get(jf.name)
    if (!file || file.size !== jf.size) throw new Error(`${jf.name} is missing from the selection.`)
    let offset = 0
    let failures = 0
    while (offset < file.size) {
      try {
        const r = await call(`/api/jobs/${encodeURIComponent(job.id)}/files/${i}?offset=${offset}`, {
          method: 'POST', headers: { 'content-type': 'application/octet-stream' },
          body: file.slice(offset, Math.min(offset + CHUNK_BYTES, file.size)),
        })
        sent += r.received - offset
        offset = r.received
        failures = 0
        onProgress(sent, total)
      } catch (err) {
        const status = (err as { status?: number }).status ?? 0
        if ((status && status < 500 && status !== 409) || ++failures > MAX_RETRIES) throw err
        await new Promise((ok) => setTimeout(ok, 2 ** failures * 1000))
        const server = (await call(`/api/jobs/${encodeURIComponent(job.id)}/files/${i}`)).received as number
        sent += server - offset
        offset = server
      }
    }
  }
  await call(`/api/jobs/${encodeURIComponent(job.id)}/start`, { method: 'POST' })
  return job.id
}
