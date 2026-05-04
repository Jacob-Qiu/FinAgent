{{
    "description": "基于本地新KB检索财报/公告/filing证据块，返回可直接作为LLM上下文使用的内容、元数据和相关性分数。工具会自动基于 kb/company_aliases.yaml 从 query 中识别公司别名并转换为 ticker filter；多家公司会分别按 ticker 检索后合并返回。如果 query 中没有明确公司实体，工具会尝试调用本地 LLM router，结合股票池的 name/aliases/theme 从候选池中选择要检索的 ticker。",
    "parameters": {{
        "query": {{"type": "str", "description": "用户查询文本"}},
        "n_results": {{"type": "int", "description": "返回的财报证据块数量（默认为5）"}},
        "filters": {{"type": "dict", "description": "可选过滤条件，支持 ticker/tickers、period_end、report_type、statement_type、chunk_roles、expand_neighbors、max_content_chars、per_ticker_results、enable_entity_router、max_router_tickers，例如 {{'ticker': 'AAPL', 'period_end': '20231231', 'report_type': 'annual_report', 'statement_type': 'income_statement', 'max_content_chars': 3500}}。财报工具默认 expand_neighbors=false、max_content_chars=3500，以避免表格页返回过长；如果需要更多上下文，可显式设置 expand_neighbors=true 或调大 max_content_chars。如果不传 ticker，工具会尝试从自然语言 query 中自动识别；识别不到明确公司时，会默认启用 LLM router 从股票池中选择相关 ticker。"}}
    }},
    "required": [
        "query"
    ]
}}
