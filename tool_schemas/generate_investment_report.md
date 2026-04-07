{{
    "description": "生成股票投资组合报告。**此工具会自动获取所需的所有数据**，包括股票数据、指数数据、财经新闻、热门新闻等，无需先调用其他工具获取数据。",
    "parameters": {{
        "user_requirement": {{"type": "str", "description": "用户需求描述，从用户原始需求中获取"}},
        "save_to_file": {{"type": "bool", "description": "是否存储报告。如果用户没有指定，**不要**生成此参数，会自动使用默认值（True）"}},
        "file_path": {{"type": "str", "description": "报告存储路径。如果用户没有指定路径，**不要**生成此参数，会自动使用默认路径（当前项目路径下的reports文件夹中）"}}
    }},
    "required": [
        "user_requirement"
    ]
}}
