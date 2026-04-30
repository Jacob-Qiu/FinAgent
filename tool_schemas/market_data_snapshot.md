{
    "description": "读取本地历史行情Parquet并生成结构化技术面摘要",
    "parameters": {
        "query": {"type": "str", "description": "公司名称、ticker 或股票代码；例如 NVDA、英伟达、0700.HK、600036"},
        "market_type": {
            "type": "str",
            "description": "市场类型，可选",
            "enum": [
                {"value": "cn", "description": "A股"},
                {"value": "us", "description": "美股"},
                {"value": "hk", "description": "港股"}
            ]
        },
        "interval": {
            "type": "str",
            "description": "数据周期，可选",
            "enum": [
                {"value": "daily", "description": "日线"},
                {"value": "weekly", "description": "周线"}
            ]
        },
        "as_of_date": {"type": "str", "description": "按截至某个日期生成快照，格式为YYYY-MM-DD"},
        "lookback_rows": {"type": "int", "description": "用于语义解释的历史窗口行数，默认120"},
        "include_raw_tail": {"type": "bool", "description": "是否附带最近样本行表格"},
        "tail_rows": {"type": "int", "description": "附带最近样本行数量，默认5"}
    },
    "required": [
        "query"
    ]
}
