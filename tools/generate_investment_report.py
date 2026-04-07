"""
创建日期：2026年03月08日
介绍：股票投资组合报告生成工具
"""

from typing import Dict, Any
from datetime import datetime
import os
import json
import asyncio


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


def generate_investment_report(user_requirement: str, save_to_file: bool = True, file_path: str = None) -> str:
    """
    生成专业的股票投资组合报告（仿照 financial_report 模式重构）

    Args:
        user_requirement (str): 用户需求描述
        save_to_file (bool): 是否保存到文件（默认为True）
        file_path (str): 文件保存路径（可选）

    Returns:
        str: 生成的Markdown格式报告或文件路径
    """
    # 分析用户需求，提取三组独立参数
    tool_params = _analysis_portfolio_params(user_requirement)
    
    # 构建报告（内部自动获取所有数据）
    report = _build_report(user_requirement, tool_params)
    
    if save_to_file:
        file_path = _save_report(report, file_path)
        # 提取报告关键数据摘要
        summary = _extract_key_data(report, file_path)
        return summary
    
    return report


def _extract_key_data(report: str, file_path: str) -> str:
    """从报告中提取第二章投资组合构建内容并翻译成中文"""
    from utils.utils import generate_text
    
    # 提取第二章内容（从 "## 2 Investment Portfolio Construction" 到 "## 3" 之前）
    import re
    section_2_match = re.search(r'## 2 Investment Portfolio Construction(.*?)(?=## 3|$)', report, re.DOTALL)
    section_2_content = section_2_match.group(1) if section_2_match else ""
    
    if not section_2_content:
        return f"报告已生成并保存到: {file_path}\n\n无法提取投资组合数据。"
    
    prompt = f"""
        # Task: Translate the following Section 2 content from English to Chinese.
        # IMPORTANT: Do NOT summarize, modify, or add any content. Just translate directly.
        # Section 2 content to translate:
        {section_2_content}
        
        # Requirements:
        1. Translate ALL content from English to Chinese
        2. Keep the exact same structure (headings, tables, lists)
        3. Do NOT change any numbers or data
        4. Do NOT add or remove any information
        5. Keep markdown formatting intact
        
        Please translate now:
    """
    
    translated_content = generate_text(prompt).strip()
    
    # 组合最终返回内容
    result = f"报告已生成并保存到: {file_path}\n\n{translated_content}"
    return result


def _analysis_portfolio_params(user_requirement: str) -> Dict[str, Dict[str, Any]]:
    """使用LLM分析用户需求，提取投资组合相关参数（返回三组独立参数）"""
    from utils.utils import generate_text
    
    param_prompt_template = """
        SYSTEM_PROMPT: {system_prompt}
        User requirement: {user_requirement}
        Task: Analyze the user's requirement and generate JSON parameters for three different tools.
        
        Requirements:
        - Extract stock codes if mentioned (e.g., "600519.SH" for Kweichow Moutai)
        - Determine time range for analysis (default to last 1 year if not specified)
        - Identify keywords for financial news search
        
        Tool 1 - stock_data (获取指定股票的历史行情数据):
           Parameters definition (MUST follow this exactly):
           - code: str (required) - 股票代码，格式示例如下：
              * - A股格式：000001.SZ
              * - 美股格式：AAPL
              * - 港股格式：00700.HK
              * - 外汇格式：USDCNH.FXCM
              * - 期货格式：CU2501.SHF
              * - 基金格式：159919.SZ
              * - 债券逆回购格式：204001.SH
              * - 可转债格式：113008.SH
              * - 期权格式：10001313.SH",
           - market_type: str (required) - 市场类型，枚举值：
             * "cn" - A股
             * "us" - 美股
             * "hk" - 港股
             * "fx" - 外汇
             * "futures" - 期货
             * "repo" - 债券逆回购
             * "convertible_bond" - 可转债
             * "options" - 期权
           - start_date: str (optional) - 起始日期，格式为YYYYMMDD，如'20250101'
           - end_date: str (optional) - 结束日期，格式为YYYYMMDD，如'20260406'
           - indicators: str (optional) - 技术指标，如'macd(12,26,9) rsi(14)'
           
        Tool 2 - index_data (获取指定股票指数的数据):
           Parameters definition (MUST follow this exactly):
           - code: str (required) - 指数代码，格式示例：000001.SH（上证指数）、399001.SZ（深证成指）
           - start_date: str (required) - 起始日期，格式为YYYYMMDD，如'20250101'
           - end_date: str (required) - 结束日期，格式为YYYYMMDD，如'20260406'
           
        Tool 3 - SearchFinancialNews (根据关键词和时间范围搜索财经资讯内容):
           Parameters definition (MUST follow this exactly):
           - keyword: str (required) - 搜索关键词，示例："股票"
           - startDate: str (optional) - 搜索开始日期，格式为YYYY-MM-DD，如'2025-04-06'
           - endDate: str (optional) - 搜索结束日期，格式为YYYY-MM-DD，如'2026-04-06'
           - page: int (optional) - 页码（默认为1）
           - pageSize: int (optional) - 每页数量（默认为20）
           
        Response format (JSON) - MUST include all three tool's parameters separately:
        {{
            "analysis": "Brief analysis of user requirement",
            "tool_params": {{
                "stock_data": {{
                    "code": "stock code or empty string if not mentioned",
                    "market_type": "cn/us/hk/etc.",
                    "start_date": "YYYYMMDD",
                    "end_date": "YYYYMMDD",
                    "indicators": ""  // optional, empty string if not needed
                }},
                "index_data": {{
                    "code": "000001.SH or other index code",
                    "start_date": "YYYYMMDD",
                    "end_date": "YYYYMMDD"
                }},
                "SearchFinancialNews": {{
                    "keyword": "search keyword in Chinese",
                    "startDate": "YYYY-MM-DD",
                    "endDate": "YYYY-MM-DD",
                    "page": 1,
                    "pageSize": 20
                }}
            }}
        }}
    """
    
    param_prompt = param_prompt_template.format(
        system_prompt=SYSTEM_PROMPT,
        user_requirement=user_requirement
    )
    
    try:
        param_response = generate_text(param_prompt).strip()
        param_data = json.loads(param_response)
        tool_params = param_data.get("tool_params", {})
        print(f"📋 投资组合参数分析结果: {tool_params}")
        return tool_params
    except Exception as e:
        print(f"⚠️ 参数分析失败，使用默认值: {str(e)}")
        today = datetime.now()
        one_year_ago = datetime(today.year - 1, today.month, today.day)
        return {
            "stock_data": {
                "code": "",
                "market_type": "cn",
                "start_date": one_year_ago.strftime("%Y%m%d"),
                "end_date": today.strftime("%Y%m%d"),
                "indicators": ""
            },
            "index_data": {
                "code": "000001.SH",
                "start_date": one_year_ago.strftime("%Y%m%d"),
                "end_date": today.strftime("%Y%m%d")
            },
            "SearchFinancialNews": {
                "keyword": "投资 股票 市场",
                "startDate": one_year_ago.strftime("%Y-%m-%d"),
                "endDate": today.strftime("%Y-%m-%d"),
                "page": 1,
                "pageSize": 20
            }
        }


def _fetch_stock_data(stock_args: Dict[str, Any]) -> str:
    """获取股票历史数据"""
    from utils.utils import _call_tool_async
    
    args = {
        "code": stock_args.get("code", ""),
        "market_type": stock_args.get("market_type", "cn"),
        "start_date": stock_args.get("start_date", ""),
        "end_date": stock_args.get("end_date", ""),
        "indicators": stock_args.get("indicators", "")
    }
    
    try:
        result = asyncio.run(_call_tool_async("stock_data", args))
        print(f"✅ 成功获取股票数据")
        return result
    except Exception as e:
        print(f"⚠️ 获取股票数据失败: {str(e)}")
        return ""


def _fetch_index_data(index_args: Dict[str, Any]) -> str:
    """获取指数数据"""
    from utils.utils import _call_tool_async
    
    args = {
        "code": index_args.get("code", "000001.SH"),
        "start_date": index_args.get("start_date", ""),
        "end_date": index_args.get("end_date", "")
    }
    
    try:
        result = asyncio.run(_call_tool_async("index_data", args))
        print(f"✅ 成功获取指数数据")
        return result
    except Exception as e:
        print(f"⚠️ 获取指数数据失败: {str(e)}")
        return ""


def _fetch_financial_news(news_args: Dict[str, Any]) -> str:
    """获取财经新闻"""
    from utils.utils import _call_tool_async
    
    args = {
        "keyword": news_args.get("keyword", "投资 股票 市场"),
        "startDate": news_args.get("startDate", ""),
        "endDate": news_args.get("endDate", ""),
        "page": news_args.get("page", 1),
        "pageSize": news_args.get("pageSize", 20)
    }
    
    try:
        result = asyncio.run(_call_tool_async("SearchFinancialNews", args))
        print(f"✅ 成功获取财经新闻")
        return result
    except Exception as e:
        print(f"⚠️ 获取财经新闻失败: {str(e)}")
        return ""


def _fetch_hot_news() -> str:
    """获取7x24小时热门新闻"""
    from utils.utils import _call_tool_async
    
    try:
        result = asyncio.run(_call_tool_async("hot_news_7x24", {}))
        print(f"✅ 成功获取热门新闻")
        return result
    except Exception as e:
        print(f"⚠️ 获取热门新闻失败: {str(e)}")
        return ""


def _build_report(user_requirement: str, tool_params: Dict[str, Dict[str, Any]]) -> str:
    """构建完整报告（自动获取所有所需数据）"""
    print("\n🚀 开始构建投资组合报告...")
    print(f"   📝 用户需求: {user_requirement}")
    
    # 分别获取三组参数
    stock_args = tool_params.get("stock_data", {})
    index_args = tool_params.get("index_data", {})
    news_args = tool_params.get("SearchFinancialNews", {})
    
    # 自动获取所有数据
    print("\n📊 正在获取市场数据...")
    stock_data = _fetch_stock_data(stock_args)
    index_data = _fetch_index_data(index_args)
    financial_news = _fetch_financial_news(news_args)
    hot_news_7x24 = _fetch_hot_news()
    rag_content = ""  # todo RAG内容暂不实现
    
    # 生成报告时间
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 构建Markdown报告
    markdown_report = f"# Investment Portfolio Report\n\n"
    markdown_report += f"> Report Generated: {report_time}\n\n"
    
    # 1. 市场环境分析
    print("📈 正在生成市场环境分析...")
    markdown_report += "## 1 Market Environment Analysis and Core Logic\n\n"
    market_analysis_content = _generate_market_analysis(index_data, financial_news, hot_news_7x24)
    markdown_report += f"{market_analysis_content}\n\n"
    
    # 2. 投资组合构建
    print("💼 正在生成投资组合构建方案...")
    markdown_report += "## 2 Investment Portfolio Construction\n\n"
    portfolio_structure_content = _generate_portfolio_structure(
        user_requirement, stock_data, index_data, market_analysis_content, rag_content
    )
    markdown_report += f"{portfolio_structure_content}\n\n"
    
    # 3. 风控管理
    print("🛡️ 正在生成风险管理策略...")
    markdown_report += "## 3 Risk Management\n\n"
    risk_management_content = _generate_risk_management(user_requirement, portfolio_structure_content)
    markdown_report += f"{risk_management_content}\n\n"
    
    # 4. 未来展望与策略调整
    print("🔮 正在生成未来展望...")
    markdown_report += "## 4 Future Outlook\n\n"
    outlook_content = _generate_future_outlook(user_requirement, portfolio_structure_content, risk_management_content)
    markdown_report += f"{outlook_content}\n\n"
    
    # 5. 总结
    print("📋 正在生成总结...")
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
    markdown_report += "*This report is automatically generated by FinAgent*\n"
    
    print("\n✅ 报告构建完成！")
    return markdown_report


def _generate_market_analysis(index_data: str, financial_news: str, hot_news_7x24: str) -> str:
    """生成市场环境分析"""
    prompt = f"""
        # SYSTEM_PROMPT: {SYSTEM_PROMPT}
        # index_data: {index_data}
        # financial_news: {financial_news}
        # hot_news_7x24: {hot_news_7x24}
        # Task: Based on the provided information, generate a detailed market environment analysis, including macroeconomic environment analysis and core investment logic. 
        # IMPORTANT: Please generate all content in ENGLISH only. 
        # DO NOT generate first-level headings (## 1 xxx), as they are already defined in the main report.
        # Only generate second-level headings and below:
        # - Second level headings: "### 1.1 Subtopic", "### 1.2 Subtopic", etc.
        # - Third level headings: "#### 1.1.1 Sub-subtopic", etc.
        # Please ensure that the content is professional, accurate and in-depth.
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
        # Task: Based on the information provided, generate a detailed portfolio construction analysis.
        # IMPORTANT: Please generate all content in ENGLISH only.
        # DO NOT generate first-level headings (## 2 xxx), as they are already defined in the main report.
        # Only generate second-level headings and below:
        # - Second level headings: "### 2.1 Subtopic", "### 2.2 Subtopic", etc.
        # - Third level headings: "#### 2.1.1 Sub-subtopic", etc.
        
        Please include the following sections:

        ### 2.1 Investment Objectives
        List the following items:
        - Return Target: annual return target
        - Investment Horizon: investment period
        - Risk Tolerance: risk tolerance level
        - Benchmark Index: benchmark index for comparison

        ### 2.2 Asset Allocation Strategy
        Create a table with the following columns:
        - Asset Class: type of asset (Stocks, ETF, Cash, Bonds, etc.)
        - Weight: percentage allocation
        - Description: brief description of the allocation rationale

        ### 2.3 Sector Allocation
        Create a table with the following columns:
        - Sector: industry sector name
        - Weight: percentage allocation to this sector
        - Allocation Logic: reasoning for this sector allocation

        ### 2.4 Individual Stock Holdings
        Create a table with the following columns:
        - Stock: stock name and code
        - Weight: percentage weight in portfolio
        - Cost Price: purchase price
        - Current Price: current market price
        - Investment Logic: rationale for holding this stock

        ### 2.5 Portfolio Characteristics Analysis
        Create a table showing Market Cap Distribution with columns:
        - Type: market cap category (Large Cap, Mid Cap, Small Cap)
        - Proportion: percentage of portfolio

        **Requirements:**
        1. Use Markdown format with proper tables and lists
        2. All numerical values must be based on actual analysis and user requirements
        3. Investment logic must be professional, clear, and persuasive
        4. Keep language concise; do not add extra explanatory text
        5. Output only this section's content; no other sections needed
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
        # IMPORTANT: Please generate all content in ENGLISH only.
        # DO NOT generate first-level headings (## 3 xxx), as they are already defined in the main report.
        # Only generate second-level headings and below:
        # - Second level headings: "### 3.1 Subtopic", "### 3.2 Subtopic", etc.
        # - Third level headings: "#### 3.1.1 Sub-subtopic", etc.
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
        # Task: Generate a comprehensive future outlook analysis based on the provided information.
        # IMPORTANT: Please generate all content in ENGLISH only.
        # DO NOT generate first-level headings (## 4 xxx), as they are already defined in the main report.
        # Only generate second-level headings and below:
        # - Second level headings: "### 4.1 Subtopic", "### 4.2 Subtopic", etc.
        # - Third level headings: "#### 4.1.1 Sub-subtopic", etc.
        # Requirements:
        1. Include the following sections:
           - Macro Outlook
           - Market Outlook
           - Investment Opportunities
           - Strategy Adjustment Plan
        2. Ensure content is professional, accurate, and in-depth
        3. Keep the analysis concise but comprehensive
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
        # Task: Synthesize all the previous analysis contents to generate a concise and comprehensive summary.
        # IMPORTANT: Please generate all content in ENGLISH only.
        # DO NOT generate first-level headings (## 5 xxx), as they are already defined in the main report.
        # Only generate second-level headings and below:
        # - Second level headings: "### 5.1 Subtopic", "### 5.2 Subtopic", etc.
        # - Third level headings: "#### 5.1.1 Sub-subtopic", etc.
        # Please ensure that the content is professional, accurate and in-depth.
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
            safe_name = "Stock_Investment_Portfolio_Recommendations"
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
