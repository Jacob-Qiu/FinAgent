{{
    "description": "根据关键词和时间范围搜索财经资讯内容",
    "parameters": {{
        "keyword": {{"type": "str", "description": "搜索关键词；示例：\"股票\""}},
        "startDate": {{"type": "int", "description": "搜索开始日期，格式为YYYY-MM-DD；示例：\"2024-01-01\""}},
        "endDate": {{"type": "dict", "description": "搜索结束日期，格式为YYYY-MM-DD；示例：\"2024-03-20\""}},
        "page": {{"type": "int", "description": "页码（默认为1）"}},
        "pageSize": {{"type": "int", "description": "每页数量（默认为20）"}}
    }},
    "required": [
        "keyword"
    ]
}}
