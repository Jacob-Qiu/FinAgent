{{
    "description": "获取指定股票的历史行情数据",
    "parameters": {{
        "code": {{"type": "str", "description": "股票代码，如'000001.SZ'表示平安银行(A股)，'AAPL'表示苹果(美股)，'00700.HK'表示腾讯(港股)，'USDCNH.FXCM'表示美元人民币(外汇)，'CU2501.SHF'表示铜期货，'159919.SZ'表示沪深300ETF(基金)，'204001.SH'表示GC001国债逆回购，'113008.SH'表示可转债，'10001313.SH'表示期权合约"}},
        "market_type": {{
            "type": "str", 
            "description": "市场类型，选一个",
            "enum": [
                {{"value": "cn", "description": "A股"}},
                {{"value": "us", "description": "美股"}},
                {{"value": "hk", "description": "港股"}},
                {{"value": "fx", "description": "外汇"}},
                {{"value": "futures", "description": "期货"}},
                {{"value": "fund", "description": "债券逆回购"}},
                {{"value": "repo", "description": "基金"}},
                {{"value": "convertible_bond", "description": "可转债"}},
                {{"value": "options", "description": "期权"}}
            ]
        }},
        "start_date": {{"type": "str", "description": "起始日期，格式为YYYYMMDD，如'20230101'"}},
        "end_date": {{"type": "str", "description": "结束日期，格式为YYYYMMDD，如'20230131'"}},
        "indicators": {{
            "type": "str", 
            "description": "需要计算的技术指标，多个指标用空格分隔。若使用指标则必须明确指定参数，例如：'macd(12,26,9) rsi(14) kdj(9,3,3) boll(20,2) ma(10)'",
            "enum": [
                {{"value": "macd", "description": "MACD指标"}},
                {{"value": "rsi", "description": "相对强弱指标"}},
                {{"value": "kdj", "description": "随机指标"}},
                {{"value": "boll", "description": "布林带"}},
                {{"value": "ma", "description": "均线指标"}}
            ]
        }}
    }},
    "required": [
        "code",
        "market_type"
    ]
}}
