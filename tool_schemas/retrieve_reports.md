{{
    "description": "研报检索工具",
    "parameters": {{
        "query": {{"type": "str", "description": "用户查询文本"}},
        "n_results": {{"type": "int", "description": "返回的研报数量（默认为5）"}},
        "filters": {{"type": "dict", "description": "元数据过滤条件（例如 {{'ticker': 'NVDA'}}）"}}
    }},
    "required": [
        "query"
    ]
}}
