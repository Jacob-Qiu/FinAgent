# FinAgent

<p align="left">
  <a href="README.md">中文</a> | English
</p>

## Introduction
FinAgent is an LLM agent system for the financial field, which supports real-time data query, private knowledge retrieval, multi-step reasoning and structured output.  
The system adopts the Plan-and-Execute architecture:
(1) Plan: the agent first analyzes the user intention and generates a structured task plan; 
(2) Execute: call the process through langgraph to execute akshare query, rag retrieval and other subtasks in turn. 
(3) Replan: check whether the implementation result conforms to the expected plan, and determine whether to continue the implementation, adjust the plan, or output the final result.

## Function
- **Q&A system**: support natural language questions, such as "what is the revenue trend of Tencent in the past five years?"
- **report generation**: can generate structured company analysis report (including financial indicators, industry comparison, etc.)
- **rag architecture**: retrieve relevant research report fragments based on local vector database to improve the accuracy of answers
- **real time data access**: dynamically obtain stock quotes, financial data, etc. through akshare tool
- **mcp service interface**: provide standardized communication protocol to facilitate front-end or external system calls

## Structure
```
FinAgent/
├── agent.py # Core agent logic: coordinating rag, tool call and LLM generation
│
├── tool_schemas/ # Tool definitions
├── tools/ # Tool module
│
├── utils/ # Utility functions
│ ├── __init__.py
│ ├── config.py # Load config file
│ ├── mcp.py # MCP server and client configuration
│ ├── memory.py # Memory module
│ ├── nodes.py # LangGraph nodes
│ ├── rag.py # RAG
│ ├── utils.py # other
│
├── llm/ # LLM
│ ├── __init__.py
│ ├── gemini_client.py # gemini model
│ └── ollama_client.py # ollama model
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

#### Method 1: Using Startup Script (Recommended)
The startup script will automatically start the FinanceMCP Server and FinAgent.

- **Windows**: Double-click `start.bat`
- **Linux / macOS**: Run `./start.sh` or `bash start.sh` in terminal

#### Method 2: Manual Start
If you need to start each service separately, you can do it manually:

```bash
# 1. Start FinanceMCP Server
npx -y finance-mcp-http

# 2. Start FinAgent in another terminal
uv run python agent.py
```