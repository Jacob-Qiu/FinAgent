# FinAgent

<p align="left">
  中文 | <a href="README-en.md">English</a>
</p>

## 简介
在金融投资和研究场景中，用户问题往往具有多跳性、数据依赖性和逻辑复杂性。因此，我们做了FinAgent。 FinAgent是一个面向金融领域的LLM agent系统，支持实时数据查询、私有知识检索、多步推理和结构化输出。 
系统采用Plan-and-Execute结构：
（1）Plan：agent首先分析用户意图，生成结构化的任务计划；
（2）Execute：通过LangGraph调用流程，依次执行akshare查询、RAG检索等子任务。
（3）Replan：检查执行结果是否符合预期计划，并确定继续执行、调整计划、还是输出最终结果。

## 功能亮点

- **问答系统**：支持自然语言提问，如“腾讯近五年营收趋势如何？”
- **报告生成**：可生成结构化公司分析报告（含财务指标、行业对比等）
- **RAG 架构**：基于本地向量数据库检索相关研报片段，提升回答准确性
- **实时数据接入**：通过 AKShare 工具动态获取股票行情、财务数据等
- **MCP 服务接口**：提供标准化通信协议，便于前端或外部系统调用

## 项目结构
```
FinAgent/
├── agent.py # 核心智能体逻辑：协调 RAG、工具调用与 LLM 生成
│
├── tools/ # 工具模块
│ ├── __init__.py
│ ├── akshare_search.py
│ ├── calculator.py
│ ├── generate_financial_report.py
│ ├── generate_investment_report.py
│ ├── generate_report.py
│ ├── get_current_time.py
│ ├── report_retriever.py
│ └── ...
│
├── utils/ # 功能函数
│ ├── __init__.py
│ ├── config.py # 加载配置文件
│ ├── mcp.py # mcp客户端、服务端配置
│ ├── memory.py # 记忆模块
│ ├── nodes.py # LangGraph节点
│ ├── rag.py # RAG
│ ├── utils.py # 其他
│ └── ...
│
├── llm/ # 大模型
│ ├── __init__.py
│ ├── gemini_client.py # gemini模型
│ └── ollama_client.py # ollama模型
│
├── constants.py/ # 全局常量（TBC）
│
├── exceptions.py/ # 自定义异常（TBC）
│
├── data/
│
├── pyproject.toml
├── uv.lock
├── .python-version
├── config.yml # 配置文件
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

### 3. 配置信息
在config.yml中填写配置信息

### 4. 启动第三方MCP服务器
在这个项目中，我们使用了包括且慢等第三方项目的MCP工具。
1. 且慢
可直接连接其服务器运行，不需要本地部署
2. FinanceMCP
需要在本地部署，项目来源：https://github.com/guangxiangdebizi/FinanceMCP ，具体细节可参考该项目的README。
```bash
# 安装
npm install finance-mcp
# 启动服务器
npx -y finance-mcp-http
```

### 5. 启动服务
```bash
uv run python agent.py
```