"""
创建日期：2026年03月08日
介绍：股票投资组合报告生成工具
"""

from typing import Dict
from datetime import datetime
import os


# System Prompt - 专家投资者角色定义
SYSTEM_PROMPT = """
    Role: Expert Portfolio Manager
    Department: Investment
    Primary Responsibility: Generation of Customized Investment Portfolio Reports

    Role Description:
    As an Expert Portfolio Manager within the investment domain, your expertise is harnessed to develop bespoke Investment Portfolio Reports that cater to specific client requirements. This role demands a deep dive into market data, macroeconomic analysis, and individual stock performance to construct and analyze investment portfolios. Engaging directly with clients to gather essential information and continuously refining the report with their feedback ensures the final product precisely meets their needs and expectations.

    Key Objectives:
    Analytical Precision: Employ meticulous analytical prowess to interpret market data, identifying underlying trends and investment opportunities.
    Effective Communication: Simplify and effectively convey complex investment strategies, making them accessible and actionable to non-specialist audiences.
    Client Focus: Dynamically tailor reports in response to client feedback, ensuring the final analysis aligns with their strategic objectives.
    Adherence to Excellence: Maintain the highest standards of quality and integrity in report generation, following established benchmarks for analytical rigor.

    Performance Indicators:
    The efficacy of the Investment Portfolio Report is measured by its utility in providing clear, actionable insights. This encompasses aiding investment decision-making, pinpointing areas for portfolio optimization, and offering a lucid evaluation of the portfolio's risk and return characteristics. Success is ultimately reflected in the report's contribution to informed investment decisions and strategic planning.
"""


def generate_investment_report(
        user_requirement: str,
        stock_data: str,
        index_data: str,
        financial_news: str,
        hot_news_7x24: str,
        rag_content: str,
        save_to_file: bool = True,
        file_path: str = None) -> str:
    """
    生成专业的股票投资组合报告
    
    Args:
        user_requirement (str): 用户需求描述
        stock_data (str): 股票数据
        index_data (str): 指数数据
        financial_news (str): 金融新闻
        hot_news_7x24 (str): 7天24小时热门新闻
        rag_content (str): RAG模型内容
        save_to_file (bool): 是否保存到文件（可选）
        file_path (str): 保存文件路径（可选）
    
    Returns:
        str: 生成的Markdown格式报告
    """
    report_data = {
        'user_requirement': user_requirement,
        'stock_data': stock_data,
        'index_data': index_data,
        'financial_news': financial_news,
        'hot_news_7x24': hot_news_7x24,
        'rag_content': rag_content,

    }
    report = _build_report(report_data)

    if save_to_file:
        file_path = _save_report(report, file_path)
        return f"报告已生成并保存到: {file_path}"

    return report


def _build_report(report_data: Dict) -> str:
    """构建完整报告"""
    user_requirement = report_data['user_requirement']
    stock_data = report_data['stock_data']
    index_data = report_data['index_data']
    financial_news = report_data['financial_news']
    hot_news_7x24 = report_data['hot_news_7x24']
    rag_content = report_data['rag_content']

    # 生成报告时间
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 构建Markdown报告
    markdown_report = f"# Investment Portfolio Report\n\n"
    markdown_report += f"> Report Generated: {report_time}\n\n"
    
    # 1. 市场环境分析
    markdown_report += "## 1 Market Environment Analysis and Core Logic\n\n"
    market_analysis_content = _generate_market_analysis(index_data, financial_news, hot_news_7x24)
    markdown_report += f"{market_analysis_content}\n\n"
    
    # 2. 投资组合构建
    markdown_report += "## 2 Investment Portfolio Construction\n\n"
    portfolio_structure_content = _generate_portfolio_structure(user_requirement, stock_data, index_data, market_analysis_content, rag_content)
    markdown_report += f"{portfolio_structure_content}\n\n"
    
    # 3. 风控管理
    markdown_report += "## 3 Risk Management\n\n"
    risk_management_content = _generate_risk_management(user_requirement, portfolio_structure_content)
    markdown_report += f"{risk_management_content}\n\n"
    
    # 4. 未来展望与策略调整
    markdown_report += "## 4 Future Outlook\n\n"
    outlook_content = _generate_future_outlook(user_requirement, portfolio_structure_content, risk_management_content)
    markdown_report += f"{outlook_content}\n\n"
    
    # 5. 总结
    markdown_report += "## 5 Summary\n\n"
    summary_content = _generate_summary(market_analysis_content, portfolio_structure_content, risk_management_content, outlook_content)
    markdown_report += f"{summary_content}\n\n"
    
    # 6. 风险提示
    markdown_report += "## Investment Risk Disclaimer\n\n"
    markdown_report += "1. This report is for reference only and does not constitute investment advice\n"
    markdown_report += "2. Investment involves risks, please invest with caution\n"
    markdown_report += "3. It is recommended to make independent judgments based on multiple sources of information\n"
    markdown_report += "4. Past performance does not guarantee future results\n\n"
    
    markdown_report += "---\n"
    markdown_report += "*This report is automatically generated by FinAgent*"
    
    return markdown_report


def _generate_market_analysis(index_data: str, financial_news: str, hot_news_7x24: str) -> str:
    """生成市场环境分析"""
    prompt = f"""
        # SYSTEM_PROMPT: {SYSTEM_PROMPT}
        # index_data: {index_data}
        # financial_news: {financial_news}
        # hot_news_7x24: {hot_news_7x24}
        # Task: Based on the provided information, generate a detailed market environment analysis, including macroeconomic environment analysis and core investment logic. Use markdown format. Please ensure that the content is professional, accurate and in-depth.
    """
    from utils.utils import generate_text
    analysis = generate_text(prompt).strip()
    return analysis


def _generate_portfolio_structure(
        user_requirement: str, 
        stock_data: str, 
        index_data: str, 
        market_analysis_content: str, 
        rag_content: str) -> str:
    """生成投资组合构建内容"""
    prompt = f"""
        # SYSTEM_PROMPT: {SYSTEM_PROMPT}
        # user_requirement: {user_requirement}
        # stock_data: {stock_data}
        # index_data: {index_data}
        # market_analysis_content: {market_analysis_content}
        # rag_content: {rag_content}
        # Task: Based on the information provided, generate a detailed portfolio construction analysis.Please follow this exact format:

        ## 2.1 Investment Objectives
        - Return Target: [Fill in specific annual return target, e.g., 15-20%]
        - Investment Horizon: [Fill in investment period, e.g., 3-5 years]
        - Risk Tolerance: [Fill in risk tolerance, e.g., moderate-high]
        - Benchmark Index: [Fill in benchmark index, e.g., ChiNext Index]

        ## 2.2 Asset Allocation Strategy
        | Asset Class | Weight | Description |
        |---|---|---|
        | Stocks | [e.g., 85%] | [Fill in stock allocation description] |
        | ETF | [e.g., 10%] | [Fill in ETF allocation description] |
        | Cash | [e.g., 5%] | [Fill in cash allocation description] |
        | Others | [if any] | [Fill in other assets description] |

        ## 2.3 Sector Allocation
        | Sector | Weight | Allocation Logic |
        |---|---|---|
        | Technology | 35% | AI sector boom |
        | [Sector Name] | [Weight] | [Allocation Logic] |
        | [Sector Name] | [Weight] | [Allocation Logic] |

        ## 2.4 Individual Stock Holdings
        | Stock | Weight | Cost Price | Current Price | Investment Logic |
        |---|---|---|---|---|
        | [Stock Name] | [Weight] | [Cost Price] | [Current Price] | [Investment Logic] |
        | [Stock Name] | [Weight] | [Cost Price] | [Current Price] | [Investment Logic] |

        ## 2.5 Portfolio Characteristics Analysis
        Market Cap Distribution:
        | Type | Proportion |
        |---|---|
        | Large Cap | [e.g., 50%] |
        | Mid Cap | [e.g., 35%] |
        | Small Cap | [e.g., 15%] |

        **Requirements:**
        1. Strictly follow the Markdown format above, including tables, lists, and heading hierarchy
        2. Tables must include all columns with reasonable content
        3. Numerical values must align with the actual portfolio situation
        4. Investment logic must be professional, clear, and persuasive
        5. Keep language concise; do not add extra explanatory text
        6. Output only this section's content; no other sections needed
    """
    from utils.utils import generate_text
    analysis = generate_text(prompt).strip()
    return analysis


def _generate_risk_management(user_requirement: str, portfolio_structure_content: str) -> str:
    """生成风控管理内容"""
    prompt = f"""
        # SYSTEM_PROMPT: {SYSTEM_PROMPT}
        # user_requirement: {user_requirement}
        # portfolio_structure_content: {portfolio_structure_content}
        # Task: Generate a comprehensive risk management analysis based on the provided information.
        # Requirements:
        1. Use Markdown format with proper tables and paragraphs
        2. Include the following sections:
           - Position Building Strategy
           - Rebalancing Strategy
           - Risk Control Measures
           - Risk Monitoring Metrics
        3. Ensure content is professional, accurate, and in-depth
        4. Keep the analysis concise but comprehensive
    """
    from utils.utils import generate_text
    analysis = generate_text(prompt).strip()
    return analysis


def _generate_future_outlook(user_requirement: str, portfolio_structure_content: str, risk_management_content: str) -> str:
    """生成未来展望"""
    prompt = f"""
        # SYSTEM_PROMPT: {SYSTEM_PROMPT}
        # user_requirement: {user_requirement}
        # portfolio_structure_content: {portfolio_structure_content}
        # risk_management_content: {risk_management_content}
        # Task: 基于提供的未来展望和市场分析数据，生成一份详细的未来展望与策略调整分析，包括宏观展望、市场展望、投资机会和策略调整计划。使用Markdown格式，包括段落和列表。请确保内容专业、准确、有深度。
        # Task: Generate a comprehensive future outlook analysis based on the provided information.
        # Requirements:
        1. Include the following sections:
           - Macro Outlook
           - Market Outlook
           - Investment Opportunities
           - Strategy Adjustment Plan
        2. Ensure content is professional, accurate, and in-depth
        3. Keep the analysis concise but comprehensives
    """
    from utils.utils import generate_text
    analysis = generate_text(prompt).strip()
    return analysis


def _generate_summary(market_analysis: str, portfolio_structure: str, risk_management: str, future_outlook: str) -> str:
    """生成总结"""
    prompt = f"""
        # SYSTEM_PROMPT: {SYSTEM_PROMPT}
        # market_analysis: {market_analysis}
        # portfolio_structure: {portfolio_structure}
        # risk_management: {risk_management}
        # future_outlook: {future_outlook}
        # Task: Synthesize all the previous analysis contents to generate a concise and comprehensive summary. Use the markdown format. Please ensure that the content is professional, accurate and in-depth.
    """
    from utils.utils import generate_text
    summary = generate_text(prompt).strip()
    return summary


def _save_report(report_content: str, file_path: str = None) -> str:
    """
    保存报告到文件

    Args:
        report_content (str): 要保存的报告内容
        file_path (str): 指定的文件路径，如果为None则自动生成
        portfolio_name (str): 投资组合名称，用于生成文件名

    Returns:
        str: 实际保存的文件路径

    Raises:
        Exception: 当文件保存失败时抛出
    """
    try:
        # 确定文件路径
        if not file_path:
            # 自动生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = "Stock Investment Portfolio Recommendations"
            filename = f"{safe_name}_{timestamp}.md"

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
        raise Exception(f"保存报告失败: {str(e)}")