"use client";

import { useState } from "react";
import { ApiError } from "@/lib/api";
import { KnowledgeSearchResult, searchKnowledge } from "@/lib/labApi";

/** The research lab's Knowledge / RAG view: search the project's own knowledge base (the
 * index the AI explanations cite), or a temporary index built from your documents. Results
 * are retrieved passages with their source, never generated text. */
export default function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [result, setResult] = useState<KnowledgeSearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(await searchKnowledge(query, files));
    } catch (err) {
      setError((err as ApiError).detail ?? String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-16">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">Knowledge search</h1>
        <p className="mt-1 text-sm text-foreground-muted">
          Search the documents RULGuard&apos;s explanations cite: project decisions, dataset audits and
          papers. Or add your own PDF, Markdown, TXT or DOCX files to search them instead; they are
          indexed for this search only and never stored.
        </p>
      </header>

      <form onSubmit={(e) => void search(e)} className="flex flex-col gap-4 rounded-xl border border-surface-border bg-surface p-4">
        <label className="flex flex-col gap-1 text-sm font-medium">
          Question or keywords
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. why is RUL withheld for some XJTU bearings?"
            className="rounded-lg border border-surface-border bg-background px-3 py-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Your documents (optional, up to 10 files, 20 MB)
          <input
            type="file"
            multiple
            accept=".pdf,.md,.txt,.docx"
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            className="text-sm"
          />
        </label>
        <button
          type="submit"
          disabled={busy || (!query.trim() && files.length === 0)}
          className="self-start rounded-full border-2 border-surface-border bg-mint px-5 py-2 font-display text-sm font-bold disabled:opacity-60"
        >
          {busy ? "Searching…" : files.length ? "Index and search" : "Search"}
        </button>
      </form>

      {error && <p className="text-sm text-danger">{error}</p>}

      {result && (
        <section className="flex flex-col gap-3">
          <p className="text-sm text-foreground-muted">
            {result.index === "built-in" ? "Project knowledge base" : "Your documents"}: {result.documents}{" "}
            document(s), {result.chunks} passage(s) indexed.
          </p>
          {result.files.length > 0 && (
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="text-foreground-muted">
                  <th className="py-1">File</th>
                  <th className="py-1">Status</th>
                  <th className="py-1 text-right">Passages</th>
                </tr>
              </thead>
              <tbody>
                {result.files.map((f) => (
                  <tr key={f.file} className="border-t border-surface-border">
                    <td className="py-1 pr-3">{f.file}</td>
                    <td className="py-1 pr-3">
                      {f.status}
                      {f.reason && ` (${f.reason})`}
                    </td>
                    <td className="py-1 text-right tabular-nums">{f.chunks}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {query.trim() && result.hits.length === 0 && (
            <p className="text-sm">No relevant passage found for this query.</p>
          )}
          {result.hits.map((h) => (
            <article key={`${h.source}-${h.chunk_id}`} className="rounded-xl border border-surface-border bg-surface p-4">
              <p className="text-xs font-semibold text-foreground-muted">
                {h.source}
                {h.page ? `, p.${h.page}` : ""} · relevance {h.score.toFixed(3)}
              </p>
              <p className="mt-2 text-sm whitespace-pre-line">{h.text}</p>
            </article>
          ))}
        </section>
      )}
    </main>
  );
}
