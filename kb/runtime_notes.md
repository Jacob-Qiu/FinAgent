# Runtime Notes

## Current extension-layer status

- `pyarrow` is required for Parquet writes and has been installed in the current local environment.
- `pandas`, `akshare`, and `pyarrow` are importable in the current local environment.
- The KB pipeline now expects `qdrant-client` and uses `BAAI/bge-m3` via `sentence-transformers`.

## Verified runtime caveats

- A-share, US, and HK requests through `AkShare` may fail if the local proxy intercepts upstream finance endpoints.

## Recommended local environment adjustments

- Let domestic financial hosts bypass the proxy when you run A-share jobs.
- Keep market jobs small during verification, then batch by market/theme instead of all symbols at once.
- Put secrets into env vars or a private `config_ext.local.yml` file rather than committing them into the repository.
- Expect the first BGE-M3 load to download model weights the first time you run the KB build.
- If you point Qdrant at a local path, keep that path out of version control.

## Suggested env vars

- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `TUSHARE_TOKEN`
- `FINNHUB_API_KEY`
- `QIEMAN_URL`
- `QDRANT_URL`
- `QDRANT_API_KEY`
