# FinAgent

<p align="right">
  English | <a href="README.md">中文</a>
</p>

## Introduction
【待补充简介】

## Function

- **问答系统**：支持自然语言提问，如“腾讯近五年营收趋势如何？”
- **报告生成**：可生成结构化公司分析报告（含财务指标、行业对比等）
- **RAG 架构**：基于本地向量数据库检索相关研报片段，提升回答准确性
- **实时数据接入**：通过 AKShare 工具动态获取股票行情、财务数据等
- **MCP 服务接口**：提供标准化通信协议，便于前端或外部系统调用

## 项目结构
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
│ ├── summary.py # History information process
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

## 快速开始（使用 uv）

### 1. 安装 uv（若尚未安装）

```bash
# Linux / macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```


### 2. 克隆项目并创建虚拟环境

```bash
# 在父文件夹下克隆远程仓库
git clone git@github.com:Jacob-Qiu/FinAgent.git
cd FinAgent

# 使用 uv 自动创建虚拟环境并安装依赖
uv sync
```
uv sync 会：
* 根据 .python-version 或系统默认 Python 创建 .venv
* 从 pyproject.toml 安装所有依赖（包括 dev 依赖）

### 3. 启动服务
```bash
uv run python agent.py
```