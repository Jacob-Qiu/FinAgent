{{
    "description": "获取指定股票指数的数据",
    "parameters": {{
        "code": {{
            "type": "str", 
            "description": "指数代码，格式示例如下：
                - 上证指数：000001.SH
                - 深证成指：399001.SZ
        "}},
        "start_date": {{"type": "str", "description": "起始日期，格式为YYYYMMDD，如'20230101'"}},
        "end_date": {{"type": "str", "description": "结束日期，格式为YYYYMMDD，如'20230131'"}},
    }},
    "required": [
        "code",
        "start_date",
        "end_date"
    ]
}}
