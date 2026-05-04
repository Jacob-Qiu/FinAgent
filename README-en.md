# FinAgent

<p align="left">
  <a href="README.md">中文</a> | English
</p>

## Introduction

FinAgent is an LLM agent system for the financial domain, supporting real-time data query, private knowledge retrieval, multi-step reasoning, and structured output.
The system adopts a Plan-and-Execute architecture:
(1) **Plan**: the agent first analyzes user intent and generates a structured task plan;
(2) **Execute**: calls the workflow through LangGraph to sequentially execute sub-tasks such as AKShare queries and RAG retrieval;
(3) **Replan**: checks whether execution results match the expected plan and determines whether to continue execution, adjust the plan, or output the final result.

## Feature Highlights

- **Q&A System**: supports natural language questions, e.g., "What is Tencent's revenue trend over the past five years?"
- **Report Generation**: can generate structured company analysis reports (including financial indicators, industry comparisons, etc.)
- **RAG Architecture**: retrieves relevant research report fragments from a local vector database to improve answer accuracy
- **Real-time Data Access**: dynamically fetches stock quotes and financial data via AKShare
- **MCP Service Interface**: provides a standardized communication protocol for frontend or external system integration

## Project Structure

```
FinAgent/
├── agent.py # Core agent logic: coordinating RAG, tool calls, and LLM generation
│
├── tool_schemas/ # Tool definitions
├── tools/ # Tool modules
│
├── utils/ # Utility functions
│ ├── __init__.py
│ ├── config.py # Configuration file loader
│ ├── mcp.py # MCP client and server configuration
│ ├── memory.py # Memory module
│ ├── nodes.py # LangGraph nodes
│ ├── utils.py # Miscellaneous utilities
│
├── llm/ # Large language models
│ ├── __init__.py
│ ├── gemini_client.py # Gemini model
│ └── ollama_client.py # Ollama model
│
├── pyproject.toml
├── uv.lock
├── .python-version
├── config.yml # Configuration file
├── README-en.md
├── README.md
├── start.bat # Startup script (Windows)
└── start.sh # Startup script (Linux / macOS)
```

## Quick Start (uv)

### 1. Install uv

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Clone Project and Create Virtual Environment

```bash
# Clone remote repository under the parent folder
git clone git@github.com:Jacob-Qiu/FinAgent.git
cd FinAgent

# Use uv to automatically create virtual environment and install dependencies
uv sync
```

`uv sync` will:
- Create `.venv` based on `.python-version` or the system default Python
- Install all dependencies (including dev dependencies) from `pyproject.toml`

### 3. Configuration

Fill in the configuration information in `config.yml`.

### 4. Start Third-party MCP Servers

This project uses third-party MCP tools including Qieman and others.

1. **Qieman**
   Can be connected directly to its server for operation — no local deployment required.

2. **FinanceMCP**
   Requires local deployment. Project source: https://github.com/guangxiangdebizi/FinanceMCP — see the project's README for details.

```bash
# Install
npm install finance-mcp
```

### 5. Data Update Rhythm

`agent_ext.py` is an extension entry for manually maintaining data assets and does not automatically start the dialogue system. It is recommended to use it on the following schedule:

```bash
# Incrementally update local historical market Parquet before each formal use of the agent
uv run python agent_ext.py build-history

# After adding or modifying research reports, financial reports, or announcements, slice, vectorize, and write the raw corpus to the KB
uv run python agent_ext.py build-kb --doc-types report,filing
```

Default raw corpus locations:
- `kb/raw_reports/`: Research reports, brokerage reports
- `kb/raw_filings/`: Financial reports, announcements, SEC filings, annual/quarterly reports

**Future optimization for financial table processing**: The current KB construction primarily extracts PDF/HTML financial reports into plain text, then slices by chapter and sentence — grouping every two sentences into a chunk, with any odd final sentence as a standalone chunk, and using a fallback split only when content exceeds the token limit. This approach is suitable for narrative content such as management discussions, risk factors, and audit opinions. For strongly structured content like income statements, balance sheets, and cash flow statements, table/layout parsing should be added in the future to restore fields like account names, periods, amounts, and units into structured JSON or Markdown tables, stored as independent structured evidence blocks — avoiding the destruction of account-value mappings caused by plain text slicing.

**Future optimization for financial report retrieval quality**: Current financial report retrieval can complete ingestion, ticker filtering, vector recall, keyword recall, and context return. However, questions about Chinese financial metrics such as "revenue, profit, cash flow, gross margin" are still affected by English financial terminology differences. For example, "收入" in English financial reports often corresponds to `revenue`, `net sales`, or `sales`, not `income`. Future improvements should include Chinese-English financial term expansion and field synonym mapping; add `period_end` time priority weighting for questions like "latest financial report" to prioritize the most recent quarterly/annual reports; and structure content like the three statements, segment revenue, product revenue, and key operating metrics as independent evidence blocks so that metric-based questions preferentially match structured financial data rather than relying on plain text chunks.

**Future optimization for retrieval ranking**: The current KB retrieval fuses vector recall, SQLite keyword recall, and a set of code rules to generate a `rerank_score` before selecting evidence. This score includes vector ranking, keyword ranking, ticker/date/title/chapter/body hits, and other factors — interpretability and stability still have room for improvement. Future work could make rule weights configurable and add clearer debug output to explain why a particular piece of evidence ranks at the top.

**Future optimization for real-time market data**: The current real-time market data tool still uses the logic of "first pulling a market snapshot, then filtering stocks locally" — fetching the entire real-time list for A-shares, Hong Kong stocks, and US stocks, then filtering out stocks the user cares about. This approach is stable but introduces unnecessary fetching overhead when querying a single stock. If a more suitable upstream API can be found, it is recommended to change to fetching real-time market data directly by the stock code provided by the user, avoiding the need to filter from a full market snapshot.

**KB retrieval object routing**: Both `retrieve_reports` and `retrieve_filings` share the entity recognition logic in `kb/company_aliases.yaml`. They first map company aliases in the user question to a ticker, then filter research reports or financial reports by ticker. If the question does not specify a company entity (e.g., "Recommend a few stocks in the tech sector"), the tool attempts to call a local LLM router, which selects tickers to retrieve from the candidate pool based on `name`, `aliases`, and `theme` in the stock pool. The router is only responsible for selecting retrieval targets, not directly generating investment conclusions. If the local model is unavailable, it falls back to full-database retrieval.

### 6. Start Service

#### Method 1: Using Startup Script (Recommended)

The startup script automatically starts FinanceMCP Server and FinAgent.

- **Windows**: Double-click `start.bat`
- **Linux / macOS**: Run `./start.sh` or `bash start.sh` in the terminal

#### Method 2: Manual Start

If you need to start each service separately, you can execute manually:

```bash
# 1. Start FinanceMCP Server
npx -y finance-mcp-http

# 2. Start FinAgent in another terminal
uv run python agent.py
```

### 7. Testing Guide
For more testing instructions, please refer to the [User Guide](FinAgent_User_Instruction.md)
