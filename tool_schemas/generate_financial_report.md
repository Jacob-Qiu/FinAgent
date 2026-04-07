{{
    "description": "生成公司财务分析报告",
    "parameters": {{
        "user_requirement": {{"type": "str", "description": "用户需求、前序步骤执行结果"}},
        "save_to_file": {{"type": "bool", "description": "是否存储报告（默认为True）"}},
        "file_path": {{"type": "str", "description": "报告存储路径。如果用户没有指定路径，**不要**生成此参数，会自动使用默认路径（当前项目路径下的reports文件夹中）"}}
    }},
    "required": [
        "user_requirement"
    ]
}}
