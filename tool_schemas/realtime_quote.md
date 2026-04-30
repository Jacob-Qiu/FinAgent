{
    "description": "通过AkShare查询A股/港股/美股实时行情，并输出适合LLM理解的价格、涨跌幅、成交量和成交量异动比率快照",
    "parameters": {
        "query": {"type": "str", "description": "股票代码、ticker或公司名称，例如 600036、NVDA、0700.HK、腾讯"},
        "market_type": {
            "type": "str",
            "description": "市场类型，可选；提供后可减少代码识别歧义",
            "enum": [
                {"value": "cn", "description": "A股"},
                {"value": "us", "description": "美股"},
                {"value": "hk", "description": "港股"}
            ]
        },
        "include_raw": {"type": "bool", "description": "是否附带标准化原始行情行，默认false"}
    },
    "required": [
        "query"
    ]
}
