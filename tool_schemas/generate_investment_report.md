{{
    "description": "生成股票投资组合报告",
    "parameters": {{
        "user_requirement": {{"type": "str", "description": "用户需求描述，从用户原始需求中获取"}},
        "stock_data": {{"type": "str", "description": "股票数据，从前序步骤执行结果中获取，若前序步骤无法获取有效信息则为空字符串"}},
        "index_data": {{"type": "str", "description": "公司综合表现，从前序步骤执行结果中获取，若前序步骤无法获取有效信息则为空字符串"}},
        "financial_news": {{"type": "str", "description": "新闻，从前序步骤执行结果中获取，若前序步骤无法获取有效信息则为空字符串"}},
        "hot_news_7x24": {{"type": "str", "description": "7天24小时热门新闻，从前序步骤执行结果中获取，若前序步骤无法获取有效信息则为空字符串"}},
        "rag_content": {{"type": "str", "description": "公司研报等，从前序步骤执行结果中获取，若前序步骤无法获取有效信息则为空字符串"}},
        "save_to_file": {{"type": "bool", "description": "是否存储报告（可选，默认为True）"}},
        "file_path": {{"type": "str", "description": "报告存储路径（可选，默认为项目路径的reports/文件夹中）"}}
    }},
    "required": [
        "user_requirement",
        "stock_data",
        "index_data",
        "financial_news",
        "hot_news_7x24",
        "rag_content"
    ]
}}
