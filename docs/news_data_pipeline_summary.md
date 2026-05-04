# 新闻数据工程总结

本文记录当前 FinAgent 中两条已经落地的新闻数据链路：

- `SearchFinancialNews`：基于 Qieman 的定向新闻检索
- `hot_news_7x24`：基于 AkShare 的 7x24 热门新闻聚合

两条链路在工程结构上都遵循同一类处理思想：先取数，再做结构化清洗、去重合并、主体锚定、逻辑/情绪打标，最后输出给 Agent 直接消费的 Markdown 简报。

## 1. SearchFinancialNews

### 数据来源
- 通过 Qieman MCP 按 `keyword + time range` 拉取财经快讯。
- 更适合公司、行业、宏观主题的定向新闻检索。

### 处理流程
1. 原始 JSON 标准化为统一字段。
2. 结构化降噪，过滤低价值内容。
3. 时间窗聚类，先把同主题快讯聚成簇。
4. 主体锚定，提取涉及实体并围绕查询关键词判断。
5. 调用本地 Ollama 通用模型生成 JSON 简报。
6. 再由代码层做语义去重、情绪纠偏、逻辑纠偏和 Markdown 渲染。

### 当前效果
- 能稳定输出适合 LLM 直接消费的简报。
- 对“同一事件多家媒体重复报道”已经能进行合并。
- 对“竞争对手增强 -> 核心实体利空”这类立场判断已加入通用规则。

## 2. hot_news_7x24

### 数据来源
- 当前改为本地 AkShare 聚合，不再依赖 Tushare / FinanceMCP。
- 更适合“市场广谱热点流”的实时观察。

### 处理流程
1. AkShare 抓取热门快讯并统一成标准字段。
2. 结构化降噪，先过滤投教、直播、路演、纯评论等噪音。
3. 时间窗聚类，合并高相似快讯簇。
4. 主体/市场实体锚定，保留公司、国家、资产、板块或行业等具体对象。
5. 调用本地 Ollama 通用模型做二次压缩和标签生成。
6. 代码层再次去重、纠偏、排序，最终输出 Markdown 简报。

### 重点优化
- 7x24 热门新闻不再只是“标题列表”，而是面向决策的结构化简报。
- 对政务、外交、政策发布、会议报道等同主题快讯，增加了更强的合并提示，尽量避免重复占用 token。

## 3. 共同输出格式

两条链路最终都会输出类似下面的单行 Markdown：

```markdown
- [时间] 标题/摘要 | 来源：A/B | 实体：... | 情绪：[利好/利空/中性] | 逻辑：[竞争叙事/基本面支撑/宏观扰动/政策监管/政策支持/市场博弈/供需变化/其他]
```

这样做的目标是：

- 减少原始新闻噪音
- 避免重复事件浪费 token
- 让 Agent 更快识别事件方向和影响对象

## 4. 当前限制

现在这两条链路都依赖本地通用模型完成最终清洗与标签生成。这个方案已经可用，但仍有几个明显短板：

- 利好 / 利空 的细粒度判断仍会偶尔跑偏
- 同主题事件的合并仍有少量边界案例
- 对复杂叙事的稳定性还不如专门训练过的金融模型

### 后续方向
- 继续积累高质量样本
- 考虑把当前的清洗结果整理成训练集
- 后续微调或训练成金融领域的专家模型，提高立场判断、语义合并和逻辑打标的稳定性

## 5. 代码位置

- `SearchFinancialNews` 清洗逻辑：[`/Users/maowenyuan/Desktop/FinAgent/FinAgent/tools/news_briefing.py`](/Users/maowenyuan/Desktop/FinAgent/FinAgent/tools/news_briefing.py)
- `hot_news_7x24` AkShare 抓取：[`/Users/maowenyuan/Desktop/FinAgent/FinAgent/tools/hot_news_feed.py`](/Users/maowenyuan/Desktop/FinAgent/FinAgent/tools/hot_news_feed.py)
- 工具路由：[`/Users/maowenyuan/Desktop/FinAgent/FinAgent/utils/utils.py`](/Users/maowenyuan/Desktop/FinAgent/FinAgent/utils/utils.py)
- MCP 服务器挂载：[`/Users/maowenyuan/Desktop/FinAgent/FinAgent/utils/mcp.py`](/Users/maowenyuan/Desktop/FinAgent/FinAgent/utils/mcp.py)

