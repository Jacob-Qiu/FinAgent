{{
    "description": "生成公司财务分析报告",
    "parameters": {{
        "user_requirement": {{"type": "str", "description": "用户通过对话提出的报告需求"}},
        "save_to_file": {{"type": "bool", "description": "是否存储报告（默认为True）"}},
        "file_path": {{"type": "str", "description": "报告存储路径（默认为项目路径的reports/文件夹中）"}}
    }},
    "required": [
        "user_requirement"
    ]
}}
