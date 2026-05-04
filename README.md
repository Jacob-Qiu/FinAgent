# FinAgent

<p align="left">
  中文 | <a href="README-en.md">English</a>
</p>

## 简介
FinAgent是一个面向金融领域的LLM agent系统，支持实时数据查询、私有知识检索、多步推理和结构化输出。 
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
├── tool_schemas/ # 工具定义
├── tools/ # 工具模块
│
├── utils/ # 功能函数
│ ├── __init__.py
│ ├── config.py # 加载配置文件
│ ├── mcp.py # mcp客户端、服务端配置
│ ├── memory.py # 记忆模块
│ ├── nodes.py # LangGraph节点
│ ├── utils.py # 其他
│
├── llm/ # 大模型
│ ├── __init__.py
│ ├── gemini_client.py # gemini模型
│ └── ollama_client.py # ollama模型
│
├── pyproject.toml
├── uv.lock
├── .python-version
├── config.yml # 配置文件
├── README-en.md
├── README.md
├── start.bat # 启动脚本（Windows）
└── start.sh # 启动脚本（Linux / macOS）
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
```

### 5. 数据更新节奏

`agent_ext.py` 是手动维护数据资产的扩展入口，不会自动启动对话系统。建议按下面节奏使用：

```bash
# 每天或每次正式使用 agent 前，增量更新本地历史行情 Parquet
uv run python agent_ext.py build-history

# 新增或修改研报、财报、公告等文件后，将本地原始语料切片、向量化并写入 KB
uv run python agent_ext.py build-kb --doc-types report,filing
```

原始语料默认放在：

- `kb/raw_reports/`：研报、券商报告
- `kb/raw_filings/`：财报、公告、SEC filing、年报/季报

财报表格处理的后续优化方向：当前 KB 构建主要将 PDF/HTML 财报抽取为纯文本后按章节和句子切片，同一段落内每两个句子组成一个 chunk，奇数最后一句单独成 chunk，并仅在内容超过 token 上限时做兜底切分，适合管理层讨论、风险因素、审计意见等叙述性内容；对于利润表、资产负债表、现金流量表等强表格结构内容，后续应增加表格/版面解析，将科目、期间、金额、单位等字段还原为结构化 JSON 或 Markdown Table，再作为独立的表格证据块入库，以避免纯文本切片破坏科目与数值的对应关系。

财报检索质量的后续优化方向：当前财报检索已经可以完成入库、ticker 过滤、向量召回、关键词召回和上下文返回，但对“收入、利润、现金流、毛利率”等中文财务指标问题仍容易受到英文财报术语差异影响，例如“收入”在英文财报中常对应 `revenue`、`net sales`、`sales`，而不是 `income`。后续应增加中英文财务术语扩展和字段同义词映射；对“最近财报”这类问题增加 `period_end` 时间优先权重，优先召回最新季报/年报；同时将三张表、分部收入、产品收入、关键经营指标等内容结构化为独立证据块，使指标类问题优先命中结构化财务数据，而不是依赖普通文本切片。

检索排序的后续优化方向：当前 KB 检索会融合向量召回、SQLite 关键词召回和一组代码规则，生成 `rerank_score` 后再选取证据；该分数包含向量排名、关键词排名、ticker/日期/标题/章节/正文命中等多种因素，解释性和稳定性仍有优化空间。后续可将规则权重配置化，并增加更清晰的调试输出，以便判断某条证据为何排在前面。

实时行情的后续优化方向：当前实时行情工具仍采用“先拉市场快照、再本地筛股票”的逻辑，也就是先获取 A 股、港股、美股的整张实时列表，再从列表里筛出用户关心的股票。这样实现稳定，但在查询单只股票时会带来不必要的抓取开销。后续如果能找到更合适的上游接口，建议改成按用户输入的股票代码直接获取对应股票的实时行情，避免从整市场快照里再筛选。

KB 检索对象路由：`retrieve_reports` 和 `retrieve_filings` 共用 `kb/company_aliases.yaml` 的实体识别逻辑，会先将用户问题中的公司别名映射为 ticker，再按 ticker 过滤研报或财报；如果问题没有明确公司实体（如“科技领域推荐几只股票”），工具会尝试调用本地 LLM router，结合股票池里的 `name`、`aliases`、`theme` 从候选池中选择要检索的 ticker。router 只负责选择检索对象，不直接生成投资结论；若本地模型不可用，则退回原始全库检索。

### 6. 启动服务

#### 方式一：使用启动脚本（推荐）
启动脚本会自动启动 FinanceMCP Server 和 FinAgent。

- **Windows**: 双击 `start.bat`
- **Linux / macOS**: 在终端运行 `./start.sh` 或 `bash start.sh`

#### 方式二：手动启动
如果需要分别启动各个服务，可以手动执行：

```bash
# 1. 启动 FinanceMCP Server
npx -y finance-mcp-http

# 2. 在另一个终端启动 FinAgent
uv run python agent.py
```

### 7. 测试指引
更多测试使用指引请参考[使用指引](FinAgent_User_Instruction.md)