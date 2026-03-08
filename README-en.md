# FinAgent

<p align="left">
  <a href="README.md">中文</a> | English
</p>

## Introduction
【待补充简介】

## Function
- **Q&A system**: support natural language questions, such as "what is the revenue trend of Tencent in the past five years?"
- **report generation**: can generate structured company analysis report (including financial indicators, industry comparison, etc.)
- **rag architecture**: retrieve relevant research report fragments based on local vector database to improve the accuracy of answers
- **real time data access**: dynamically obtain stock quotes, financial data, etc. through akshare tool
- **mcp service interface**: provide standardized communication protocol to facilitate front-end or external system calls

## Structure
```
FinAgent/
├── mcp_server.py # MCP Server
├── agent.py # Core agent logic: coordinating rag, tool call and LLM generation
│
├── tools/ # Tool module
│ ├── init.py
│ ├── akshare_search.py
│ ├── calculator.py
│ ├── generate_report.py
│ ├── get_current_time.py
│ └── ...
│
├── utils/ # Utility functions
│ ├── init.py
│ ├── config_loader.py # Load config file
│ ├── nodes.py # LangGraph nodes
│ ├── memory.py # History information process
│ ├── utils.py # General utility functions
│ └── ...
│
├── constants.py/ # Global constants（TBC）
│
├── exceptions.py/ # Exceptions（TBC）
│
├── rag/ # RAG components
│ ├── vector_store.py # Vector database management
│ └── retriever.py # Retrieval logic
│
├── data/
│ ├── reports/ # Research report of 20 companies in recent 10 years (pdf/txt)
│ └── ...
│
├── pyproject.toml
├── .python-version
├── config.yml # Configuration file
├── README-en.md
└── README-cn.md
```

## Quick Start (uv)

### 1. Intsall uv

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```


### 2. Clone project and create virtual environment

```bash
# Clone remote warehouse under parent folder
git clone git@github.com:Jacob-Qiu/FinAgent.git
cd FinAgent

# Use UV to automatically create virtual environments and install dependencies
uv sync
```
UV sync will:
* Create.Venv according to.Python version or the system default Python
* Install all dependencies (including dev dependencies) from pyproject.toml

### 3 Configuration information
Fill in the configuration information in config.yml

### 4 Start the third-party MCP server
In this project, we use MCP tools for third-party projects such as Qieman.

1. Qieman
It can be directly connected to its server for operation without local deployment

2. FinanceMCP
It needs to be deployed locally. Project source: https://github.com/guangxiangdebizi/FinanceMCP For details, please refer to the README of the project.

```bash
# Install
npm install finance-mcp
# Start MCP Service
npx -y finance-mcp-http
```

### 5. Start Service
```bash
uv run python agent.py
```