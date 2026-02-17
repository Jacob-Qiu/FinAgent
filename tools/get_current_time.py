"""
创建日期：2026年02月17日
介绍：获取当前时间工具函数
"""

from datetime import datetime
from typing import Dict, Union


def get_current_time(time_format: str = "standard") -> Union[str, Dict]:
    """
    获取当前时间
    
    Args:
        time_format (str): 时间格式，默认为"standard"
                          可选值：
                          - standard: 标准格式 YYYY-MM-DD HH:MM:SS
                          - timestamp: Unix时间戳
                          - detailed: 详细信息字典
                          - chinese: 中文格式 YYYY年MM月DD日 HH时MM分SS秒
    
    Returns:
        Union[str, Dict]: 根据format参数返回不同格式的时间信息
        
    Raises:
        ValueError: 当time_format参数不支持时抛出
    """
    try:
        now = datetime.now()
        
        if time_format == "standard":
            return now.strftime("%Y-%m-%d %H:%M:%S")
        elif time_format == "timestamp":
            return str(int(now.timestamp()))
        elif time_format == "detailed":
            return {
                "year": now.year,
                "month": now.month,
                "day": now.day,
                "hour": now.hour,
                "minute": now.minute,
                "second": now.second,
                "weekday": now.weekday(),  # 0=Monday, 6=Sunday
                "iso_format": now.isoformat(),
                "timestamp": int(now.timestamp())
            }
        elif time_format == "chinese":
            return now.strftime("%Y年%m月%d日 %H时%M分%S秒")
        else:
            raise ValueError(f"不支持的时间格式: {time_format}")
            
    except Exception as e:
        raise Exception(f"获取当前时间失败: {str(e)}")


def test_get_current_time():
    """
    测试函数：展示get_current_time返回的不同格式
    """
    print("=" * 60)
    print("get_current_time 测试函数 - 不同格式展示")
    print("=" * 60)
    
    # 测试不同格式
    test_formats = [
        {"format": "standard", "desc": "标准格式"},
        {"format": "timestamp", "desc": "Unix时间戳"},
        {"format": "chinese", "desc": "中文格式"},
        {"format": "detailed", "desc": "详细信息"}
    ]
    
    for i, case in enumerate(test_formats, 1):
        print(f"\n测试案例 {i}: {case['desc']}")
        print(f"时间格式: {case['format']}")
        print("-" * 40)
        
        try:
            result = get_current_time(case['format'])
            if isinstance(result, dict):
                print("返回数据类型: Dictionary")
                print("数据内容:")
                for key, value in result.items():
                    print(f"  {key}: {value}")
            else:
                print("返回数据类型: String")
                print(f"时间: {result}")
                    
        except Exception as e:
            print(f"❌ 错误: {str(e)}")
        
        print("=" * 60)


if __name__ == "__main__":
    # 直接运行此文件时执行测试
    test_get_current_time()