# Database Structure

Lean local-first storage. No server, no ORM.

- **Raw archives/CSVs**: external, immutable, read-only. Paths configured in `config/data_paths.toml` (gitignored - private absolute paths never committed).
- **Fixtures**: tiny real-data excerpts committed under `data/fixtures/` for tests only.
- **Derived feature tables**: Parquet under `data/processed/` (gitignored, regenerable).
- **DuckDB** (`artifacts/metadata.duckdb`, gitignored): metadata, lineage, experiment records, metrics, predictions, report references. See `docs/database-schema.md`.
- **Models**: scikit-learn pipelines via Joblib (`artifacts/models/`). Optional neural models in their native format (M6+).
- **Vector index**: FAISS (`artifacts/indices/`, M7, deferred past review).
- **Figures/metrics/PDF**: files under `reports/`, referenced by path + checksum from DuckDB rows, not stored as blobs in the DB.

## Why raw sensor rows are not in DuckDB
Full college run is ~18GB across 129 files of ~2M rows each; FEMTO has ~28 bearings x hundreds-to-thousands of 2560-row acquisitions. DuckDB stores identifiers, schema version, Parquet paths, and hashes - not the wide feature vectors or raw samples themselves. This keeps the database small, fast, and diffable, and keeps the "bounded memory" requirement honest.
