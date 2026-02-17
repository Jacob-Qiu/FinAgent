"""
创建日期：2026年02月17日
介绍：股票数据搜索工具，基于akshare获取实时股票信息
"""

import akshare as ak
import pandas as pd
from typing import Dict, List, Union, Optional


def akshare_search(stock_code: str, data_type: str = "realtime", start_date: str = None, end_date: str = None) -> Union[pd.DataFrame, Dict]:
    """
    通过akshare获取股票数据
    
    Args:
        stock_code (str): 股票代码，支持多种格式：
                         - A股：如 "000001" 或 "sh600000"
                         - 港股：如 "00700" 或 "hk00700"
                         - 美股：如 "AAPL" 或 "BABA"
        data_type (str): 数据类型，默认为"realtime"
                        可选值：realtime(实时行情)、history(历史数据)、info(基本信息)
        start_date (str): 开始日期，格式为"YYYYMMDD"，仅在data_type="history"时有效
        end_date (str): 结束日期，格式为"YYYYMMDD"，仅在data_type="history"时有效
    
    Returns:
        Union[pd.DataFrame, Dict]: 返回股票数据，格式根据data_type而定
        
    Raises:
        ValueError: 当股票代码无效或不支持时抛出
        Exception: 当akshare接口调用失败时抛出
    """
    try:
        # 标准化股票代码格式
        normalized_code = _normalize_stock_code(stock_code)
        
        if data_type == "realtime":
            return _get_realtime_data(normalized_code)
        elif data_type == "history":
            return _get_history_data(normalized_code, start_date=start_date, end_date=end_date)
        elif data_type == "info":
            return _get_stock_info(normalized_code)
        else:
            raise ValueError(f"不支持的数据类型: {data_type}")
            
    except Exception as e:
        raise Exception(f"获取股票数据失败: {str(e)}")


def _normalize_stock_code(stock_code: str) -> str:
    """标准化股票代码格式"""
    code = stock_code.strip().upper()
    
    # 处理A股代码
    if code.startswith(('SH', 'SZ')):
        return code.lower()
    elif code.isdigit() and len(code) == 6:
        # 自动识别上海或深圳交易所
        if code.startswith(('6', '5')):
            return f"sh{code}"
        else:
            return f"sz{code}"
    
    # 港股代码处理
    elif code.startswith('HK') or (code.isdigit() and len(code) == 5):
        if code.startswith('HK'):
            return code.lower()
        else:
            return f"hk{code}"
    
    # 美股代码保持原样
    else:
        return code.lower()


def _get_realtime_data(stock_code: str) -> pd.DataFrame:
    """获取实时行情数据"""
    try:
        # 判断市场类型
        if stock_code.startswith('sh') or stock_code.startswith('sz'):
            # A股实时行情
            df = ak.stock_zh_a_spot_em()
            # 筛选指定股票
            result = df[df['代码'] == stock_code[2:]]
            if result.empty:
                raise ValueError(f"未找到股票代码: {stock_code}")
            return result
        elif stock_code.startswith('hk'):
            # 港股实时行情
            df = ak.stock_hk_spot_em()
            result = df[df['代码'] == stock_code[2:]]
            if result.empty:
                raise ValueError(f"未找到港股代码: {stock_code}")
            return result
        else:
            # 美股实时行情
            df = ak.stock_us_spot_em()
            result = df[df['代码'].str.upper() == stock_code.upper()]
            if result.empty:
                raise ValueError(f"未找到美股代码: {stock_code}")
            return result
            
    except Exception as e:
        raise Exception(f"获取实时行情失败: {str(e)}")


def _get_history_data(stock_code: str, period: str = "daily", start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """获取历史数据
    
    Args:
        stock_code (str): 股票代码
        period (str): 数据周期，默认为"daily"
        start_date (str): 开始日期，格式为"YYYYMMDD"，默认为None（最早数据）
        end_date (str): 结束日期，格式为"YYYYMMDD"，默认为None（最新数据）
    
    Returns:
        pd.DataFrame: 历史数据DataFrame
    """
    try:
        if stock_code.startswith('sh') or stock_code.startswith('sz'):
            # A股历史数据
            if start_date and end_date:
                return ak.stock_zh_a_hist(symbol=stock_code[2:], period=period, start_date=start_date, end_date=end_date)
            else:
                return ak.stock_zh_a_hist(symbol=stock_code[2:], period=period)
        elif stock_code.startswith('hk'):
            # 港股历史数据
            if start_date and end_date:
                return ak.stock_hk_hist(symbol=stock_code[2:], period=period, start_date=start_date, end_date=end_date)
            else:
                return ak.stock_hk_hist(symbol=stock_code[2:], period=period)
        else:
            # 美股历史数据
            if start_date and end_date:
                return ak.stock_us_hist(symbol=stock_code.upper(), period=period, start_date=start_date, end_date=end_date)
            else:
                return ak.stock_us_hist(symbol=stock_code.upper(), period=period)
            
    except Exception as e:
        raise Exception(f"获取历史数据失败: {str(e)}")


def _get_stock_info(stock_code: str) -> Dict:
    """获取股票基本信息"""
    try:
        if stock_code.startswith('sh') or stock_code.startswith('sz'):
            # A股基本信息
            df = ak.stock_individual_info_em(symbol=stock_code[2:])
            return df.set_index('item')['value'].to_dict()
        elif stock_code.startswith('hk'):
            # 港股基本信息（简化处理）
            return {"code": stock_code, "market": "港股", "note": "港股基础信息接口待完善"}
        else:
            # 美股基本信息（简化处理）
            return {"code": stock_code, "market": "美股", "note": "美股基础信息接口待完善"}
            
    except Exception as e:
        raise Exception(f"获取股票信息失败: {str(e)}")


def test_akshare_search():
    """
    测试函数：展示akshare_search返回的原始数据格式
    """
    print("=" * 60)
    print("akshare_search 测试函数 - 原始数据展示")
    print("=" * 60)
    
    # 测试用例
    test_cases = [
        {"code": "000001", "type": "realtime", "desc": "平安银行A股实时行情"},
        {"code": "sh600000", "type": "realtime", "desc": "浦发银行A股实时行情"},
        {"code": "000001", "type": "history", "start_date": "20260210", "end_date": "20260213", "desc": "平安银行A股2026年2月10-13日历史数据"},
        # {"code": "00700", "type": "realtime", "desc": "腾讯控股港股实时行情"},  # 可选测试
        # {"code": "AAPL", "type": "realtime", "desc": "苹果公司美股实时行情"},   # 可选测试
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n测试案例 {i}: {case['desc']}")
        print(f"股票代码: {case['code']}")
        print(f"数据类型: {case['type']}")
        print("-" * 40)
        
        try:
            if 'start_date' in case and 'end_date' in case:
                result = akshare_search(case['code'], case['type'], case['start_date'], case['end_date'])
            else:
                result = akshare_search(case['code'], case['type'])
            if isinstance(result, pd.DataFrame):
                print("返回数据类型: DataFrame")
                print(f"数据形状: {result.shape}")
                print("列名:", list(result.columns))
                print("\n前5行数据:")
                print(result.head())
                if not result.empty:
                    print("\n数据示例:")
                    for col in result.columns[:5]:  # 显示前5列
                        print(f"{col}: {result.iloc[0][col]}")
            else:
                print("返回数据类型: Dictionary")
                print("数据内容:")
                for key, value in list(result.items())[:10]:  # 显示前10项
                    print(f"  {key}: {value}")
                    
        except Exception as e:
            print(f"❌ 错误: {str(e)}")
        
        print("=" * 60)


if __name__ == "__main__":
    # 直接运行此文件时执行测试
    test_akshare_search()