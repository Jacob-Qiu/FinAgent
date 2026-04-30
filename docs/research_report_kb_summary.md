# 研报新 KB 工程总结

## 当前结论

研报新 KB 的核心工程链路已经完成：研报文件处理、去重、切片、向量化入 Qdrant、SQLite 关键词索引、用户问题解析、混合检索、rerank、邻近 chunk 展开，以及主 agent 的 `retrieve_reports` 工具入口切换，均已落到代码里。

需要如实说明的是：当前仓库里的 `kb/raw_reports/` 只有说明文件，没有真实研报样本。因此代码链路已完成并通过轻量检查，但“真实研报召回质量”仍需要在放入实际文件并执行 build 后验证。

## 已完成范围

1. 研报读取与文件处理

- 原始路径：`kb/raw_reports/`
- 支持格式：PDF、Markdown、TXT
- 文件哈希：对源文件计算 SHA-256，用于增量跳过和同文件去重
- 文件路径版本管理：同一路径文件内容变更时，会先删除旧 chunk，再写入新 chunk
- 文件名解析：优先从 `{ticker}_{publish_date}_{broker}_{subject}` 这类命名中解析 ticker、发布日期、机构和主题

2. 研报切片

- PDF：逐页抽取文本，按中文章节、标题、编号大纲做章节识别，再在章节内按 token window 切片
- Markdown/TXT：按 heading / 中文章节 / 编号大纲识别结构，再按 token window 切片
- evidence chunk：每个正文片段作为可召回证据
- summary chunk：每篇文档生成一个抽取式 summary chunk，用于文档级初筛
- payload 元数据：保存 doc_type、corpus_type、ticker、broker、publish_date、source_path、source_hash、page、section_path、chunk_index 等字段

3. 向量入库

- 向量模型：默认 `BAAI/bge-m3`
- 向量库：Qdrant
- 本地默认路径：`kb/qdrant/`
- collection：默认 `finagent_kb`
- payload index：已为 doc_type、corpus_type、chunk_role、ticker、broker、publish_date、source_hash、source_path、section_path_text、source_title 创建过滤索引

4. 关键词索引

- 本地 SQLite 索引：`kb/qdrant/kb_lexical_index.sqlite`
- 用途：补足向量检索对 ticker、机构、日期、标题、专有名词的精确匹配能力
- 索引字段：title、section path、ticker、broker、publish_date、doc_type、corpus_type、content

5. 用户问题到检索

- 查询解析：自动识别 ticker、日期，并抽取中英文关键词
- 检索方式：Qdrant 向量召回 + SQLite 关键词召回 + metadata 过滤
- 融合排序：通过 reciprocal-rank 风格的 fused score 合并向量和关键词候选
- rerank：对 evidence chunk、ticker 命中、日期命中、标题/章节/正文关键词命中加权
- 邻近展开：命中 chunk 后，会补同一章节相邻 chunk，减少答案上下文被切断的问题

6. Agent 入口

- 主工具：`retrieve_reports`
- 当前实现：`tools/report_retriever.py`
- 接入方式：`utils/mcp.py` 注册本地 MCP tool，`utils/nodes.py` 的 tool_candidates 已描述为“基于本地新 KB 检索研报证据块”
- 返回内容：不是直接把整个 KB 或特征表输出给 LLM，而是返回检索命中的 evidence chunk、metadata、score，作为 LLM 回答问题时的上下文证据

## 旧路径清理状态

旧 Chroma 路径已经从主 agent 研报检索入口移除：

- `utils/rag.py` 已删除
- `tools/report_retriever.py` 已切到 `KnowledgeBasePipeline`
- `chromadb` 依赖已从项目依赖移除
- 代码搜索未发现残留 `chroma/chromadb` 调用

## 已验证内容

- Python 编译检查通过
- `retrieve_reports` 在 mock pipeline 下可返回新 KB 格式结果
- 本地 MCP server 可创建并暴露 `retrieve_reports`
- 旧 Chroma 引用搜索已清空

## 尚未完成或待验证内容

- 尚未用真实研报 corpus 验证召回质量，因为当前 `kb/raw_reports/` 没有实际研报文件
- 尚未做 OCR 兜底和语言识别，按当前约定暂时不做
- summary chunk 是抽取式摘要，不是 LLM 生成式摘要；如果后续需要更高质量文档级摘要，可再加模型摘要步骤
