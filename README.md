# FinAgent

<p align="right">
  <a href="README-en.md">English</a> | 中文
</p>

## 简介
【待补充简介】

## 功能亮点

- **问答系统**：支持自然语言提问，如“腾讯近五年营收趋势如何？”
- **报告生成**：可生成结构化公司分析报告（含财务指标、行业对比等）
- **RAG 架构**：基于本地向量数据库检索相关研报片段，提升回答准确性
- **实时数据接入**：通过 AKShare 工具动态获取股票行情、财务数据等
- **MCP 服务接口**：提供标准化通信协议，便于前端或外部系统调用

## 项目结构
```
FinAgent/
├── mcp_server.py # MCP（Model Communication Protocol）服务入口
├── agent.py # 核心智能体逻辑：协调 RAG、工具调用与 LLM 生成
│
├── tools/ # 工具模块
│ ├── init.py
│ ├── akshare_search.py
│ ├── calculator.py
│ ├── generate_report.py
│ ├── get_current_time.py
│ └── ...
│
├── utils/ # 功能函数
│ ├── init.py
│ ├── config_loader.py # 加载配置文件
│ ├── nodes.py # LangGraph节点
│ ├── summary.py # 历史消息处理
│ ├── utils.py # 其他
│ └── ...
│
├── constants.py/ # 全局常量（TBC）
│
├── exceptions.py/ # 自定义异常（TBC）
│
├── rag/ # RAG组件
│ ├── vector_store.py # 向量数据库管理（FAISS / Chroma）
│ └── retriever.py # 检索逻辑
│
├── data/
│ ├── reports/ # 20家公司近10年研报（PDF/TXT）
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