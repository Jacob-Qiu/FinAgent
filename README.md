# FinAgent

【待补充简介】

## 功能亮点

- **问答系统**：支持自然语言提问，如“腾讯近五年营收趋势如何？”
- **报告生成**：可生成结构化公司分析报告（含财务指标、行业对比等）
- **RAG 架构**：基于本地向量数据库检索相关研报片段，提升回答准确性
- **实时数据接入**：通过 AKShare 工具动态获取股票行情、财务数据等
- **MCP 服务接口**：提供标准化通信协议，便于前端或外部系统调用

## 项目结构
FinAgent/
├── mcp_server.py # MCP（Model Communication Protocol）服务入口
├── agent.py # 核心智能体逻辑：协调 RAG、工具调用与 LLM 生成
│
├── tools/ # 工具模块
│ ├── init.py
│ ├── calculator.py
│ └── 
│
├── utils/ # 功能函数
│ ├── init.py
│ ├── nodes.py # LangGraph节点
│ ├── summary.py # 历史信息处理
│ └── utils.py # 通用功能函数
│
├── constants.py/ # 全局常量（不一定做）
│
├── exceptions.py/ # 自定义异常（不一定做）
│
├── rag/ # RAG 组件
│ ├── vector_store.py # 向量数据库管理（FAISS / Chroma）
│ └── retriever.py # 检索逻辑
│
├── data/
│ └── reports/ # 20家公司近10年研报（PDF/TXT）
│
├── config/
│ └── loader.py # 加载配置文件
│
├── pyproject.toml # 项目元数据与依赖声明
├── .python-version # 指定 Python 版本
├── config.yml # 配置文件（路径、模型参数等）
├── README-en.md
└── README-cn.md

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
git clone https://github.com/your-username/financial-agent.git
cd financial-agent

# 使用 uv 自动创建虚拟环境并安装依赖
uv sync
```
uv sync 会：
* 根据 .python-version 或系统默认 Python 创建 .venv
* 从 pyproject.toml 安装所有依赖（包括 dev 依赖）

## 3. 配置环境变量
复制模板并填入你的密钥：
```bash
cp .env.example .env
# 编辑 .env，填入 LLM API 密钥等
```

示例 .env.example 内容：
```env
LLM_API_KEY=your_openai_or_dashscope_key
```

## 4. 启动服务
```bash
# 激活虚拟环境（uv 默认使用 .venv）
source .venv/bin/activate  # Linux/macOS
# .\.venv\Scripts\activate  # Windows

# 启动 MCP 服务
python mcp_server.py
```
服务启动后，可通过 HTTP 请求交互：
```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "宁德时代2023年毛利率是多少？"}'
```