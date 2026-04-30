# 财报 Corpus 新 KB 工程总结

## 当前结论

财报 corpus 的核心工程链路已经完成初版：财报文件处理、去重、切片、元数据解析、向量化入 Qdrant、SQLite 关键词索引、用户问题解析、混合检索、metadata 过滤、rerank、邻近 chunk 展开，以及主 agent 的 `retrieve_filings` 工具入口，均已落到代码里。

需要如实说明的是：当前仓库里的 `kb/raw_filings/` 只有说明文件，没有真实财报样本。因此代码链路已完成并通过轻量检查，但“真实财报召回质量”和“不同公司/不同格式财报的解析稳定性”仍需要在放入实际文件并执行 build 后验证。

## 已完成范围

1. 财报读取与文件处理

- 原始路径：`kb/raw_filings/`
- 配置入口：`config_ext.example.yml` 的 `knowledge_base.sources.raw_filings_dir`
- 支持格式：PDF、Markdown、TXT、HTML、HTM、XHTML、XML、CSV、JSON
- 文件哈希：对源文件计算 SHA-256，用于增量跳过和同文件去重
- 文件路径版本管理：同一路径文件内容变更时，会先删除旧 chunk，再写入新 chunk
- 文件名解析：优先从 `{ticker}_{period_end}_{report_type}_{issuer/title}` 这类命名中解析 ticker、报告期、报告类型、公司主体和标题
- 推荐命名示例：`000001_20231231_annual_report_平安银行2023年年度报告.pdf`

2. 财报切片

- PDF：逐页抽取文本，按中文章节、标题、编号大纲做章节识别，再在章节内按 token window 切片
- Markdown/TXT：按 heading / 中文章节 / 编号大纲识别结构，再按 token window 切片
- HTML/XHTML/XML：先做轻量标签清洗，再按结构化文本切片
- CSV/JSON：先转为可读文本记录，再进入结构化文本切片
- evidence chunk：每个正文片段作为可召回证据
- summary chunk：每份财报生成一个抽取式 summary chunk，用于文档级初筛
- statement_type 标注：根据章节标题和正文关键词识别资产负债表、利润表、现金流量表、权益变动表、附注、管理层讨论与分析、风险因素、审计报告等章节类型
- payload 元数据：保存 doc_type、corpus_type、ticker、issuer、period_end、report_type、statement_type、source_path、source_hash、page、section_path、chunk_index 等字段

3. 向量入库

- 向量模型：默认 `BAAI/bge-m3`
- 向量库：Qdrant
- 本地默认路径：`kb/qdrant/`
- collection：默认 `finagent_kb`
- doc_type：`filing`
- corpus_type：`financial_filing`
- payload index：已为 doc_type、corpus_type、chunk_role、ticker、period_end、report_type、statement_type、issuer、source_hash、source_path、section_path_text、source_title 创建过滤索引

4. 关键词索引

- 本地 SQLite 索引：`kb/qdrant/kb_lexical_index.sqlite`
- 用途：补足向量检索对 ticker、报告期、报告类型、报表类型、公司主体、标题和专有财务科目的精确匹配能力
- 索引字段：title、section path、ticker、issuer、period_end、report_type、statement_type、doc_type、corpus_type、content
- 兼容旧索引：SQLite schema 会自动补充新增的财报字段列，避免已有 lexical index 缺列时报错

5. 用户问题到检索

- 查询解析：自动识别 ticker、明确日期、财报报告期、报告类型、报表/章节类型，并抽取中英文关键词
- 报告期识别：支持 `2023年报`、`2024中报`、`2024Q3`、`2024三季报`、`2023-12-31`、`20231231` 等常见表达
- 报告类型识别：支持 annual_report、semiannual_report、quarterly_report、10-K、10-Q、20-F、业绩快报、业绩预告、修订/更正等表达
- 报表类型识别：支持利润表、资产负债表、现金流量表、权益变动表、附注、管理层讨论与分析、风险因素、审计报告等表达
- 检索方式：Qdrant 向量召回 + SQLite 关键词召回 + metadata 过滤
- metadata 过滤：支持按 ticker、period_end、report_type、statement_type、chunk_role 过滤
- 融合排序：通过 reciprocal-rank 风格的 fused score 合并向量和关键词候选
- rerank：对 evidence chunk、ticker 命中、报告期命中、报告类型命中、报表类型命中、标题/章节/正文关键词命中加权
- 邻近展开：命中 chunk 后，会补同一章节相邻 chunk，减少财报表格或章节上下文被切断的问题

6. Agent 入口

- 主工具：`retrieve_filings`
- 当前实现：`tools/filing_retriever.py`
- 接入方式：`utils/mcp.py` 注册本地 MCP tool，`utils/utils.py` 加入 local_mcp_tools，`utils/nodes.py` 的 tool_candidates 已加入“基于本地新 KB 检索财报/公告证据块”
- 工具 schema：`tool_schemas/retrieve_filings.md`
- 默认检索范围：固定 `doc_types=["filing"]`
- 默认 chunk_role：`evidence`
- 返回内容：不是直接把整份财报或结构化特征表输出给 LLM，而是返回检索命中的 evidence chunk、metadata、score，作为 LLM 回答财报问题时的上下文证据

7. CLI 入口

- 构建入口：`python scripts/build_knowledge_base_qdrant.py build --doc-types filing`
- 全量默认构建：`python scripts/build_knowledge_base_qdrant.py build`，默认包含 `report,filing,encyclopedia,glossary`
- 检索入口：`python scripts/build_knowledge_base_qdrant.py search --query "..."`
- CLI 过滤参数：`--doc-types filing`、`--ticker`、`--period-end`、`--report-type`、`--statement-type`、`--chunk-roles`
- extension CLI：`python agent_ext.py build-kb` 和 `python agent_ext.py search-kb` 也已支持财报过滤参数

## 已验证内容

- Python 编译检查通过
- `load_extension_settings()` 可解析 `kb/raw_filings`、`filing_chunk_tokens`、`filing_chunk_overlap`
- 财报文件名解析轻量测试通过：例如 `000001_20231231_annual_report_平安银行2023年年度报告`
- 用户查询解析轻量测试通过：例如 `000001 2023年报 利润表收入` 可识别 ticker、period_end、report_type、statement_type
- 财报切片轻量测试通过：示例文本中的 `利润表` 和 `资产负债表` 可被标注为对应 statement_type
- `retrieve_filings` 在 mock pipeline 下可返回新 KB 格式结果
- 本地 MCP server 可创建并暴露 `retrieve_filings`
- `agent_ext.py show-config` 可显示财报目录和 chunk 配置
- `scripts/build_knowledge_base_qdrant.py search --help` 和 `agent_ext.py search-kb --help` 已显示财报过滤参数

## 尚未完成或待验证内容

- 尚未用真实财报 corpus 验证召回质量，因为当前 `kb/raw_filings/` 没有实际财报文件
- 尚未验证不同来源财报格式的解析稳定性，尤其是扫描版 PDF、复杂 HTML/XBRL、跨市场公告格式
- 尚未做 OCR 兜底；如果后续遇到扫描版 PDF，需要新增 OCR 或改用可抽取文本版本
- 尚未做专业表格结构化抽取；当前 CSV/JSON 会转成文本入库，PDF/HTML 表格主要按文本证据检索，而不是结构化财务三表数据库
- 尚未做指标级事实表，例如营业收入、净利润、经营现金流等字段的标准化数值库；目前目标是 RAG 证据检索，不是财务指标数据库
- summary chunk 是抽取式摘要，不是 LLM 生成式摘要；如果后续需要高质量财报摘要，可再加模型摘要步骤
- 尚未针对真实财报做 rerank 权重调优；需要真实样本 build 后观察召回结果再调
