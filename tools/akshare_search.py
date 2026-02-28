"""
创建日期：2026年02月24日
介绍：股票数据搜索工具，基于akshare获取实时股票信息，支持智能识别市场和代码
"""

import akshare as ak
import pandas as pd
from typing import Dict, List, Union, Optional
import sys
import os

# 确保可以从 utils 导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from utils.utils import generate_text
except ImportError:
    # 如果作为脚本直接运行，可能需要调整路径
    pass

def _resolve_stock_identity(query: str) -> str:
    """
    使用LLM识别输入的股票身份
    返回格式：Market|Ticker|Name
    示例：US|NVDA|英伟达
    """
    prompt = f"""
    你是一个专业的金融数据专家。请识别输入项 query 指向的上市公司。

    输入 query: {query}

    请严格按照以下格式返回结果：
    市场|标准Ticker|中文简称

    市场代码说明：
    - A: A股 (如 600519)
    - US: 美股 (如 NVDA, AAPL)
    - HK: 港股 (如 00700)

    示例：
    - “英伟达” -> US|NVDA|英伟达
    - “NVDA” -> US|NVDA|英伟达
    - “腾讯” -> HK|00700|腾讯控股
    - “00700” -> HK|00700|腾讯控股
    - “中科软” -> A|603927|中科软
    - “603927” -> A|603927|中科软
    - “贵州茅台” -> A|600519|贵州茅台

    如果无法识别或不确定，请返回 UNKNOWN|NONE|NONE。
    只返回结果字符串，不要包含任何其他内容。
    """
    
    try:
        response = generate_text(prompt).strip()
        # 清理可能存在的 markdown 标记
        response = response.replace('`', '').strip()
        # 提取第一行有效内容
        lines = response.split('\n')
        for line in lines:
            if '|' in line:
                return line.strip()
        return "UNKNOWN|NONE|NONE"
    except Exception as e:
        print(f"LLM识别失败: {e}")
        return "UNKNOWN|NONE|NONE"

def akshare_search(stock_code: str, data_type: str = "realtime", start_date: str = None, end_date: str = None) -> Union[pd.DataFrame, Dict]:
    """
    通过akshare获取股票数据，支持智能识别A股/港股/美股
    
    Args:
        stock_code (str): 股票代码或名称，如 "600519", "NVDA", "腾讯", "中科软"
        data_type (str): 数据类型，默认为"realtime"
                        可选值：realtime(实时行情)、history(历史数据)、info(基本信息)
        start_date (str): 开始日期，格式为"YYYYMMDD"
        end_date (str): 结束日期，格式为"YYYYMMDD"
    
    Returns:
        Union[pd.DataFrame, Dict]: 返回股票数据
    """
    try:
        stock_code = str(stock_code).strip()
        if not stock_code:
            raise ValueError("股票代码不能为空")

        # 支持多只股票查询（逗号分隔）
        if "," in stock_code or "，" in stock_code:
            codes = [c.strip() for c in stock_code.replace("，", ",").split(",") if c.strip()]
            multi_results = {}
            for code in codes:
                try:
                    # 递归调用单只股票查询
                    res = akshare_search(code, data_type, start_date, end_date)
                    if isinstance(res, pd.DataFrame):
                        # DataFrame 转字典以便合并
                        multi_results[code] = res.to_dict(orient="records")
                    else:
                        multi_results[code] = res
                except Exception as e:
                    multi_results[code] = f"查询失败: {str(e)}"
            return multi_results

        market = None
        ticker = None
        name = None
        
        # 1. Input Pre-check
        # 6位纯数字 -> A股
        if stock_code.isdigit() and len(stock_code) == 6:
            market = "A"
            ticker = stock_code
            name = stock_code
        # .US 后缀 -> 美股
        elif stock_code.upper().endswith(".US"):
            market = "US"
            ticker = stock_code.upper().replace(".US", "")
            name = ticker
        # .HK 后缀 -> 港股
        elif stock_code.upper().endswith(".HK"):
            market = "HK"
            ticker = stock_code.upper().replace(".HK", "")
            name = ticker
        # 包含中文或纯字母 -> LLM Routing
        else:
            print(f"调用LLM识别股票身份: {stock_code}")
            identity = _resolve_stock_identity(stock_code)
            print(f"LLM识别结果: {identity}")
            
            parts = identity.split('|')
            if len(parts) >= 2 and parts[0] in ["A", "US", "HK"]:
                market = parts[0]
                ticker = parts[1]
                name = parts[2] if len(parts) > 2 else ticker
            else:
                # Fallback: 如果是纯字母，尝试作为美股处理，或者是A股拼音？
                # 这里保守起见，如果无法识别则报错
                raise ValueError(f"无法识别该公司的股票代码: {stock_code}，请尝试提供准确的股票代码或标准名称。")

        # 3. Market Execution
        if market == "A":
            return _handle_a_share(ticker, data_type, start_date, end_date)
        elif market == "US":
            return _handle_us_share(ticker, data_type, start_date, end_date)
        elif market == "HK":
            return _handle_hk_share(ticker, data_type, start_date, end_date)
        else:
             raise ValueError(f"不支持的市场类型: {market}")
             
    except Exception as e:
        raise Exception(f"获取股票数据失败 ({stock_code}): {str(e)}")

def _handle_a_share(ticker: str, data_type: str, start_date: str = None, end_date: str = None):
    """处理A股查询"""
    # 简单的A股代码标准化
    # AKShare 接口通常接受纯数字代码，或者 sh/sz 前缀
    # stock_zh_a_spot_em 返回的代码是纯数字
    
    if data_type == "realtime":
        df = ak.stock_zh_a_spot_em()
        # 精确匹配代码
        result = df[df['代码'] == ticker]
        if result.empty:
             raise ValueError(f"未找到A股代码: {ticker}")
        return result
    elif data_type == "history":
        if start_date and end_date:
            return ak.stock_zh_a_hist(symbol=ticker, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        else:
            return ak.stock_zh_a_hist(symbol=ticker, period="daily", adjust="qfq")
    elif data_type == "info":
        df = ak.stock_individual_info_em(symbol=ticker)
        return df.set_index('item')['value'].to_dict()
    else:
        raise ValueError(f"不支持的数据类型: {data_type}")

def _handle_hk_share(ticker: str, data_type: str, start_date: str = None, end_date: str = None):
    """处理港股查询"""
    # 确保5位代码
    if ticker.isdigit() and len(ticker) < 5:
        ticker = ticker.zfill(5)
        
    if data_type == "realtime":
        df = ak.stock_hk_spot_em()
        result = df[df['代码'] == ticker]
        if result.empty:
            raise ValueError(f"未找到港股代码: {ticker}")
        return result
    elif data_type == "history":
        if start_date and end_date:
            return ak.stock_hk_hist(symbol=ticker, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        else:
            return ak.stock_hk_hist(symbol=ticker, period="daily", adjust="qfq")
    elif data_type == "info":
         return {"code": ticker, "market": "HK", "note": "港股基础信息接口待完善"}
    else:
        raise ValueError(f"不支持的数据类型: {data_type}")

def _handle_us_share(ticker: str, data_type: str, start_date: str = None, end_date: str = None):
    """处理美股查询"""
    ticker = ticker.upper()
    
    # 优先解析带前缀的完整代码（AKShare美股接口通常需要前缀，如 105.NVDA）
    full_symbol = ticker
    
    # 尝试通过实时接口获取完整代码
    try:
        df = ak.stock_us_spot_em()
        # 匹配 symbol 后缀 (例如 105.NVDA -> NVDA)
        matches = [code for code in df['代码'] if code.endswith(f".{ticker}")]
        if not matches:
             # 尝试直接匹配
            matches = [code for code in df['代码'] if code == ticker]
            
        if matches:
            full_symbol = matches[0]
        elif data_type == "realtime":
            # 如果是实时查询且找不到，直接报错
             raise ValueError(f"未找到美股代码: {ticker}")
    except Exception as e:
        if data_type == "realtime":
            raise e
        # 历史查询时如果实时接口失败，尝试继续使用原始ticker（虽然可能失败）
        pass

    if data_type == "realtime":
        # 上面已经获取了df，这里直接返回筛选结果
        return df[df['代码'] == full_symbol]
        
    elif data_type == "history":
        if start_date and end_date:
            return ak.stock_us_hist(symbol=full_symbol, period="daily", start_date=start_date, end_date=end_date, adjust="qfq")
        else:
            return ak.stock_us_hist(symbol=full_symbol, period="daily", adjust="qfq")
            
    elif data_type == "info":
        return {"code": ticker, "market": "US", "note": "美股基础信息接口待完善"}
    else:
        raise ValueError(f"不支持的数据类型: {data_type}")

def test_akshare_search():
    """
    测试函数：展示akshare_search返回的原始数据格式
    """
    print("=" * 60)
    print("akshare_search 测试函数 - 原始数据展示")
    print("=" * 60)
    
    # 测试用例
    test_cases = [
        {"code": "600519", "type": "realtime", "desc": "贵州茅台(代码) A股实时"},
        {"code": "中科软", "type": "realtime", "desc": "中科软(中文名) A股实时"},
        {"code": "NVDA", "type": "realtime", "desc": "英伟达(代码) 美股实时"},
        {"code": "英伟达", "type": "realtime", "desc": "英伟达(中文名) 美股实时"},
        {"code": "00700", "type": "realtime", "desc": "腾讯(代码) 港股实时"},
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试案例 {i}: {case['desc']}")
        print(f"输入: {case['code']}")
        print("-" * 40)
        
        try:
            result = akshare_search(case['code'], data_type=case['type'])
            if isinstance(result, pd.DataFrame):
                if result.empty:
                    print("结果: 空DataFrame")
                else:
                    print(f"结果: \n{result.iloc[0].to_dict()}")
            else:
                print(f"结果: {result}")
        except Exception as e:
            print(f"错误: {e}")

if __name__ == "__main__":
    test_akshare_search()
