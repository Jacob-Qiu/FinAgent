# FinAgent User Instructions

This guide explains how to set up FinAgent after downloading the project from GitHub, how to configure the required models and MCP services, where to place test research-report and filing PDFs, and how to build local historical market data and the RAG knowledge base.

## 1. Environment Requirements

FinAgent requires the following runtime environment:

- Python 3.12
- `uv` for Python dependency management
- Node.js and npm for FinanceMCP
- An LLM provider API key, or a local Ollama model

Install `uv` if it is not already installed:

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Clone the repository and install Python dependencies:

```bash
git clone <YOUR_REPO_URL>
cd FinAgent

uv sync
```

The core Python dependencies are defined in `pyproject.toml` and `uv.lock`, including:

- `akshare` for real-time and historical market data
- `fastmcp`, `mcp` for MCP tool integration
- `langgraph` for agent workflow structure
- `sentence-transformers` for local embedding models
- `pypdf`, `tiktoken`, `pyyaml`, `pydantic`, `httpx`, `yfinance`

The extension-layer KB pipeline also requires local Qdrant, Parquet, and Gemini client support. If these packages are not already installed in the environment, install them with:

```bash
uv pip install qdrant-client pyarrow google-genai
```

Optional packages for better local memory keyword retrieval:

```bash
uv pip install rank-bm25 jieba
```

Install Node dependencies:

```bash
npm install
```

FinanceMCP can also be started directly with:

```bash
npx -y finance-mcp-http
```

## 2. Model Configuration

FinAgent uses three types of models internally:

1. Main agent LLM: used for planning, parameter generation, replanning, and final answer generation.
2. KB embedding model: used to vectorize research reports, filings, encyclopedia entries, and glossary entries.
3. Memory embedding model: used by the conversation memory module.

### Main Agent LLM

The main agent LLM is configured in `config.yml`.

Supported providers:

```yaml
llm_provider: openrouter  # options: openrouter, gemini, ollama
```

For OpenRouter:

```yaml
openrouter:
  api_key: "<YOUR_OPENROUTER_API_KEY>"
  model: "deepseek/deepseek-v4-flash"
  base_url: "https://openrouter.ai/api/v1"
  timeout_seconds: 60
```

For Gemini:

```yaml
gemini:
  api_key: "<YOUR_GEMINI_API_KEY>"
  model: "gemini-2.5-flash"
```

For local Ollama:

```yaml
ollama:
  base_url: "http://localhost:11434/api/chat"
  model: "qwen3"
```

### KB Embedding Model

The RAG knowledge base uses `BAAI/bge-m3` through `sentence-transformers`.

The default extension configuration is:

```yaml
knowledge_base:
  embedding:
    model: "BAAI/bge-m3"
    batch_size: 32
```

On the first KB build, allow the embedding model to be downloaded from Hugging Face:

```bash
FINAGENT_KB_EMBEDDING_ONLINE=1 uv run python agent_ext.py build-kb --doc-types report,filing
```

After the model has been cached locally, `build-kb` can be run without `FINAGENT_KB_EMBEDDING_ONLINE=1`.

### Memory Embedding Model

The conversation memory module uses:

```text
paraphrase-multilingual-MiniLM-L12-v2
```

This model is used for episodic-memory vector search, not for the main RAG knowledge base.

## 3. Third-Party MCP Configuration

Configure external MCP services in `config.yml`:

```yaml
mcpServers:
  qieman: "<YOUR_QIEMAN_MCP_SSE_URL>"
  finmcp:
    url: "http://localhost:3000/mcp"
    token: "<YOUR_TUSHARE_TOKEN>"
```

`qieman` is used for financial news search.

`finmcp` is used for external financial-data tools and should be started with:

```bash
npx -y finance-mcp-http
```

## 4. Download and Place Test PDFs

FinAgent does not automatically download test PDF files from links. Please download the provided test research reports and filings manually, or use `curl -L`, then place them in the correct raw-data folders before building the KB.

### Research Reports

Research reports should be placed in:

```text
kb/raw_reports/
```

Supported formats:

- `.pdf`
- `.md`
- `.markdown`
- `.txt`

Recommended filename format:

```text
ticker_publishdate_broker_subject.pdf
```

Example:

```bash
mkdir -p kb/raw_reports

curl -L "<TEST_RESEARCH_REPORT_PDF_URL>" \
  -o "kb/raw_reports/GOOGL_20260401_TestBroker_Google_research_report.pdf"
```

### Financial Filings, Annual Reports, and Quarterly Reports

Financial filings should be placed in:

```text
kb/raw_filings/
```

Supported formats:

- `.pdf`
- `.md`
- `.markdown`
- `.txt`
- `.html`
- `.htm`
- `.xhtml`
- `.xml`
- `.csv`
- `.json`

Recommended filename format:

```text
ticker_periodend_reporttype_issuer_or_title.pdf
```

Example:

```bash
mkdir -p kb/raw_filings

curl -L "<TEST_FILING_PDF_URL>" \
  -o "kb/raw_filings/GOOGL_20251231_annual_report_Alphabet_10-K.pdf"
```

The ticker in the filename is important. For example, Google / Alphabet documents should start with `GOOGL_`. Otherwise, `retrieve_reports` and `retrieve_filings` may not be able to filter evidence by company correctly.

## 5. Build Local Historical Market Data

Historical market data is built from the configured stock universe:

```text
kb/stock_universe.yaml
```

Build all configured stocks, including daily and weekly data:

```bash
uv run python agent_ext.py build-history --market all --interval all --start-date 2018-01-01
```

The processed Parquet files will be saved to:

```text
data/market_data/{market}/{interval}/{symbol}.parquet
```

Examples:

```text
data/market_data/us/daily/GOOGL.parquet
data/market_data/us/weekly/GOOGL.parquet
```

Build only one stock:

```bash
uv run python agent_ext.py build-history --market us --symbols GOOGL --interval all
```

The historical market-data pipeline downloads raw market data, standardizes fields, calculates technical indicators such as MA, RSI, MACD, Bollinger Bands, volume metrics, and then writes the final data into Parquet files.

## 6. Build the RAG Knowledge Base

After placing PDFs into `kb/raw_reports/` and `kb/raw_filings/`, build the KB:

```bash
FINAGENT_KB_EMBEDDING_ONLINE=1 uv run python agent_ext.py build-kb --doc-types report,filing
```

If the embedding model is already cached locally:

```bash
uv run python agent_ext.py build-kb --doc-types report,filing
```

The processed vector database and lexical index will be stored in:

```text
kb/qdrant/
kb/qdrant/kb_lexical_index.sqlite
```

The KB pipeline reads raw files, extracts text, chunks documents, generates embeddings, writes vectors to Qdrant, and writes lexical search metadata into SQLite.

If many test PDFs have been replaced and a clean rebuild is needed:

```bash
FINAGENT_KB_EMBEDDING_ONLINE=1 uv run python agent_ext.py build-kb --doc-types report,filing --rebuild
```

Do not run `agent.py` and `build-kb` at the same time. The local Qdrant database uses file-based storage and may be locked by the running agent process.

## 7. Verify Data Was Indexed

Search research reports:

```bash
uv run python agent_ext.py search-kb \
  --query "Google AI business and cloud revenue" \
  --doc-types report \
  --ticker GOOGL
```

Search filings:

```bash
uv run python agent_ext.py search-kb \
  --query "Alphabet annual report revenue operating income" \
  --doc-types filing \
  --ticker GOOGL
```

If no results are returned, check:

- Whether the PDF is in the correct folder
- Whether the filename starts with the correct ticker, such as `GOOGL_`
- Whether `build-kb` finished successfully
- Whether `agent.py` was running while building the KB
- Whether the embedding model was available locally or allowed to download

## 8. Start FinAgent

Recommended startup:

```bash
bash start.sh
```

Manual startup:

Terminal 1:

```bash
npx -y finance-mcp-http
```

Terminal 2:

```bash
uv run python agent.py
```

After startup, the agent can use:

- `market_data_snapshot` to read local historical market data
- `realtime_quote` to fetch real-time quotes and enrich them with local historical context
- `retrieve_reports` to search indexed research reports
- `retrieve_filings` to search indexed filings, annual reports, and quarterly reports
- `SearchFinancialNews` to search recent financial news through Qieman MCP

## 9. Important Note About `agent_ext.py`

`agent_ext.py` is not a one-click interactive agent entrypoint. It is a data-maintenance command-line entrypoint.

Use:

```bash
uv run python agent_ext.py build-history
```

to build historical market data.

Use:

```bash
uv run python agent_ext.py build-kb --doc-types report,filing
```

to process research reports and filings into the local KB.

Use:

```bash
uv run python agent.py
```

to start the interactive FinAgent GUI.
