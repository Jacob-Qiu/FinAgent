"""
创建日期：2026年02月17日
介绍：其他兜底格式的报告
"""

from typing import Dict, Union, List
import json
from datetime import datetime


def generate_markdown_report(user_requirement: str, report_content: str, save_to_file: bool = False, file_path: str = None) -> str:
    # todo 改为prompt生成内容
    """
    生成专业的Markdown格式报告
    
    Args:
        user_requirement (str): 用户对报告的具体需求描述
        report_content (str): 用于生成报告的数据内容（可以是JSON字符串或普通文本）
    
    Returns:
        str: 生成的Markdown格式报告
        
    Raises:
        Exception: 当报告生成失败时抛出
    """
    try:
        # 解析报告内容
        content_data = _parse_content_data(report_content)
        
        # 生成报告标题
        title = _generate_title(user_requirement)
        
        # 生成报告时间
        report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 构建Markdown报告
        markdown_report = f"# {title}\n\n"
        markdown_report += f"> 报告生成时间: {report_time}\n\n"
        markdown_report += "## 📋 报告概述\n\n"
        markdown_report += f"{user_requirement}\n\n"
        markdown_report += "## 📊 数据分析\n\n"
        markdown_report += f"{_format_content_section(content_data)}\n\n"
        markdown_report += "## 📈 详细分析\n\n"
        markdown_report += f"{_generate_detailed_analysis(content_data, user_requirement)}\n\n"
        markdown_report += "## ⚠️ 风险提示\n\n"
        markdown_report += f"{_generate_risk_assessment(content_data)}\n\n"
        markdown_report += "## 📝 结论与建议\n\n"
        markdown_report += f"{_generate_conclusion(content_data, user_requirement)}\n\n"
        markdown_report += "---\n"
        markdown_report += "*本报告由FinAgent自动生成*"
        
        # 如果需要保存到文件
        if save_to_file:
            _save_markdown_report(markdown_report, file_path, user_requirement)
        
        return markdown_report
        
    except Exception as e:
        raise Exception(f"生成Markdown报告失败: {str(e)}")


def _parse_content_data(content: str) -> Union[Dict, str]:
    """解析报告内容数据"""
    try:
        # 尝试解析为JSON
        return json.loads(content)
    except json.JSONDecodeError:
        # 如果不是JSON，返回原文本
        return content


def _generate_title(requirement: str) -> str:
    """根据用户需求生成报告标题"""
    if "股票" in requirement or "stock" in requirement.lower():
        return "股票投资分析报告"
    elif "基金" in requirement or "fund" in requirement.lower():
        return "基金投资分析报告"
    elif "财务" in requirement or "financial" in requirement.lower():
        return "财务数据分析报告"
    else:
        return "专业分析报告"


def _format_content_section(content_data: Union[Dict, str]) -> str:
    """格式化内容数据部分"""
    if isinstance(content_data, dict):
        markdown_content = "### 原始数据\n\n"
        markdown_content += "| 字段 | 值 |\n|------|-----|\n"
        
        for key, value in content_data.items():
            markdown_content += f"| {key} | {value} |\n"
        return markdown_content
    else:
        return f"### 报告内容\n\n{content_data}"


def _generate_detailed_analysis(content_data: Union[Dict, str], requirement: str) -> str:
    """生成详细分析部分"""
    analysis = "### 分析要点\n\n"
    
    if isinstance(content_data, dict):
        # 基于数据类型生成相应的分析
        if "price" in content_data or "股价" in str(content_data):
            analysis += "- **价格分析**: "
            if "change" in content_data and float(content_data.get("change", 0)) < 0:
                analysis += "当前价格呈现下跌趋势，建议关注支撑位。\n"
            else:
                analysis += "当前价格走势相对稳定，可考虑逢低吸纳。\n"
        
        if "volume" in content_data or "成交量" in str(content_data):
            analysis += "- **成交量分析**: "
            analysis += "成交量变化反映了市场活跃度，需结合价格走势综合判断。\n"
    else:
        analysis += "- 基于提供的内容进行综合分析\n"
    
    analysis += f"- **需求匹配**: {requirement}\n"
    return analysis


def _generate_risk_assessment(content_data: Union[Dict, str]) -> str:
    """生成风险评估部分"""
    risk_text = "### 投资风险提醒\n\n"
    risk_text += "⚠️ **重要声明**\n\n"
    risk_text += "1. 本报告仅供参考，不构成投资建议\n"
    risk_text += "2. 投资有风险，入市需谨慎\n"
    risk_text += "3. 建议结合多方信息进行独立判断\n"
    risk_text += "4. 过往表现不代表未来收益\n\n"
    
    if isinstance(content_data, dict):
        if "change" in content_data:
            change_value = float(content_data.get("change", 0))
            if abs(change_value) > 5:
                risk_text += "🔴 **波动风险**: 价格波动较大，请注意风险控制\n"
    
    return risk_text


def _generate_conclusion(content_data: Union[Dict, str], requirement: str) -> str:
    """生成结论与建议部分"""
    conclusion = "### 投资建议\n\n"
    conclusion += "**综合评估**: "
    
    if isinstance(content_data, dict):
        if "change" in content_data:
            change_value = float(content_data.get("change", 0))
            if change_value > 0:
                conclusion += "短期趋势向好，可适当关注。\n"
            elif change_value < 0:
                conclusion += "短期存在回调压力，建议观望为主。\n"
            else:
                conclusion += "走势相对平稳，可根据个人风险偏好决策。\n"
        else:
            conclusion += "建议进一步收集相关信息后再做判断。\n"
    else:
        conclusion += "建议结合更多数据指标进行综合分析。\n"
    
    conclusion += "\n**操作建议**:\n"
    conclusion += "- 建议分批建仓，控制仓位风险\n"
    conclusion += "- 设置合理的止损止盈点位\n"
    conclusion += "- 关注相关政策和市场动态\n"
    
    return conclusion


def _save_markdown_report(report_content: str, file_path: str = None, user_requirement: str = "") -> str:
    """
    保存Markdown报告到文件

    Args:
        report_content (str): 要保存的报告内容
        file_path (str): 指定的文件路径，如果为None则自动生成
        user_requirement (str): 用户需求，用于生成文件名

    Returns:
        str: 实际保存的文件路径

    Raises:
        Exception: 当文件保存失败时抛出
    """
    try:
        import os

        # 确定文件路径
        if not file_path:
            # 自动生成文件名
            base_name = _generate_filename_from_requirement(user_requirement)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{base_name}_{timestamp}.md"

            # 获取当前文件所在目录的父目录
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            
            # 默认保存到reports目录
            reports_dir = os.path.join(parent_dir, "reports")
            
            if not os.path.exists(reports_dir):
                os.makedirs(reports_dir)
            file_path = os.path.join(reports_dir, filename)

        # 创建目录（如果不存在）
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory)

        # 保存文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        print(f"✅ 报告已保存到: {file_path}")
        return file_path

    except Exception as e:
        raise Exception(f"保存Markdown报告失败: {str(e)}")


def _generate_filename_from_requirement(requirement: str) -> str:
    """根据用户需求生成文件名"""
    # 提取关键词
    if "股票" in requirement:
        return "stock_analysis"
    elif "基金" in requirement:
        return "fund_analysis"
    elif "财务" in requirement:
        return "financial_analysis"
    elif "投资" in requirement:
        return "investment_analysis"
    else:
        # 清理特殊字符，生成安全的文件名
        safe_name = "".join(c for c in requirement[:20] if c.isalnum() or c in (' ', '-', '_'))
        safe_name = safe_name.replace(' ', '_')
        return safe_name or "analysis_report"


def demo_save_functionality():
    """演示文件保存功能"""
    print("🚀 Markdown报告保存功能演示")
    print("=" * 50)
    
    # 测试数据
    test_data = {
        "requirement": "请生成平安银行股票投资分析报告",
        "content": '{"name": "平安银行", "code": "000001", "price": 10.91, "change": -0.46}'
    }

    print("\n📝 演示1: 自动生成文件名保存")
    try:
        result = generate_markdown_report(
            test_data["requirement"],
            test_data["content"],
            save_to_file=True
        )
        print(f"✅ 保存成功: {result}")
    except Exception as e:
        print(f"❌ 错误: {e}")
    
    print("\n" + "=" * 50)
    print("💡 使用说明:")
    print("  • save_to_file=True: 启用文件保存功能")
    print("  • file_path参数: 指定保存路径，为None时自动生成")
    print("  • 自动生成: reports/目录下按需求类型命名")


if __name__ == "__main__":
    # 直接运行此文件时执行测试
    demo_save_functionality()