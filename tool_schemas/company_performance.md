{{
    "description": "获取指定公司的综合表现数据",
    "parameters": {{
        "ts_code": {{"type": "str", "description": "股票代码，如'000001.SZ'表示平安银行，'600000.SH'表示浦发银行"}},
        "data_type": {{
            "type": "str", 
            "description": "数据类型，选一个",
            "enum": [
                {{"value": "forecast", "description": "业绩预告"}},
                {{"value": "express", "description": "业绩快报"}},
                {{"value": "indicators", "description": "财务指标-包含盈利能力/偿债能力/营运能力/成长能力等全面指标"}},
                {{"value": "dividend", "description": "分红送股"}},
                {{"value": "mainbz", "description": "主营业务构成-融合产品/地区/行业"}},
                {{"value": "holder_number", "description": "股东人数"}},
                {{"value": "holder_trade", "description": "股东增减持"}},
                {{"value": "managers", "description": "管理层信息"}},
                {{"value": "audit", "description": "财务审计意见"}},
                {{"value": "company_basic", "description": "公司基本信息"}},
                {{"value": "balance_basic", "description": "核心资产负债表"}},
                {{"value": "balance_all", "description": "完整资产负债表"}},
                {{"value": "cashflow_basic", "description": "基础现金流"}},
                {{"value": "cashflow_all", "description": "完整现金流"}},
                {{"value": "income_basic", "description": "核心利润表"}},
                {{"value": "income_all", "description": "完整利润表"}},
                {{"value": "share_float", "description": "限售股解禁"}},
                {{"value": "repurchase", "description": "股票回购"}},
                {{"value": "top10_holders", "description": "前十大股东"}},
                {{"value": "top10_floatholders", "description": "前十大流通股东"}},
                {{"value": "pledge_stat", "description": "股权质押统计"}},
                {{"value": "pledge_detail", "description": "股权质押明细"}}
            ]
        }},
        "start_date": {{"type": "str", "description": "起始日期，格式为YYYYMMDD，如'20230101'"}},
        "end_date": {{"type": "str", "description": "结束日期，格式为YYYYMMDD，如'20231231'"}},
        "period": {{"type": "str", "description": "特定报告期，格式为YYYYMMDD，如'20231231'表示2023年年报。指定此参数时将忽略start_date和end_date"}}
    }},
    "required": [
        "ts_code",
        "data_type",
        "start_date",
        "end_date"
    ]
}}
