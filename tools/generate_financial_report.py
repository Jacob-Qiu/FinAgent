"""
创建日期：2026年03月02日
介绍：公司财务分析报告生成工具
"""

from typing import Dict, Any
from datetime import datetime
import os
import json
import asyncio

SYSTEM_PROMPT = """
    Role: Expert Investor
    Department: Finance
    Primary Responsibility: Generation of Customized Financial Analysis Reports

    Role Description:
    As an Expert Investor within the finance domain, your expertise is harnessed to develop bespoke Financial Analysis Reports that cater to specific client requirements. This role demands a deep dive into financial statements and market data to unearth insights regarding a company's financial performance and stability. Engaging directly with clients to gather essential information and continuously refining the report with their feedback ensures the final product precisely meets their needs and expectations.

    Key Objectives:
    Analytical Precision: Employ meticulous analytical prowess to interpret financial data, identifying underlying trends and anomalies.
    Effective Communication: Simplify and effectively convey complex financial narratives, making them accessible and actionable to non-specialist audiences.
    Client Focus: Dynamically tailor reports in response to client feedback, ensuring the final analysis aligns with their strategic objectives.
    Adherence to Excellence: Maintain the highest standards of quality and integrity in report generation, following established benchmarks for analytical rigor.

    Performance Indicators:
    The efficacy of the Financial Analysis Report is measured by its utility in providing clear, actionable insights. This encompasses aiding corporate decision-making, pinpointing areas for operational enhancement, and offering a lucid evaluation of the company's financial health. Success is ultimately reflected in the report's contribution to informed investment decisions and strategic planning.
"""
INCOME_ANALYSIS_PROMPT = """
    System prompt: {system_prompt}
    Raw information: {raw_information}
    User requirement: {user_requirement}
    Task: Embark on a thorough analysis of the company's income statement for the current fiscal year, focusing on revenue streams, cost of goods sold, operating expenses, and net income to discern operational performance and profitability. Examine the gross profit margin to understand cost efficiency, operating margin for operational effectiveness, and net profit margin to assess overall profitability. Compare these financial metrics against historical data to identify growth patterns, profitability trends, and operational challenges. Conclude with a strategic overview of the company's financial health, offering insights into revenue growth sustainability and potential areas for cost optimization and profit maximization in a single paragraph. The content must write in English. Please keep your analysis concise, around 100-130 words, but don't show the word counts.
"""
BALANCE_ANALYSIS_PROMPT = """
    system_prompt: {system_prompt}
    raw_information: {raw_information}
    User requirement: {user_requirement}
    Task: Delve into a detailed scrutiny of the company's balance sheet for the most recent fiscal year, pinpointing the structure of assets, liabilities, and shareholders' equity to decode the firm's financial stability and operational efficiency. Focus on evaluating liquidity through current assets versus current liabilities, solvency via long-term debt ratios, and the equity position to gauge long-term investment potential. Contrast these metrics with previous years' data to highlight financial trends, improvements, or deteriorations. Finalize with a strategic assessment of the company's financial leverage, asset management, and capital structure, providing insights into its fiscal health and future prospects in a single paragraph. The content must write in English. Please keep your analysis concise, around 100-130 words, but don't show the word counts.
"""
CASHFLOW_ANALYSIS_PROMPT = """
    system_prompt: {system_prompt}
    raw_information: {raw_information}
    User requirement: {user_requirement}
    Task: Dive into a comprehensive evaluation of company's cash flow for the latest fiscal year, focusing on cash inflows and outflows across operating, investing, and financing activities. Examine the operational cash flow to assess the core business profitability, scrutinize investing activities for insights into capital expenditures and investments, and review financing activities to understand debt, equity movements, and dividend policies. Compare these cash movements to prior periods to discern trends, sustainability, and liquidity risks. Conclude with an informed analysis of the company's cash management effectiveness, liquidity position, and potential for future growth or financial challenges in a single paragraph. The content must write in English. Please keep your analysis concise, around 100-130 words, but don't show the word counts.
"""


def generate_financial_report(user_requirement: str, save_to_file: bool = True, file_path: str = None) -> str:
    """
    生成专业的财务分析报告
    
    Args:
        user_requirement (str): 用户需求
        save_to_file (bool): 是否保存到文件
        file_path (str): 文件保存路径
    
    Returns:
        str: 生成的Markdown格式报告
    """

    company_name = _analysis_company_name(user_requirement)
    tool_args = _param_analysis(user_requirement)
    print(tool_args)
    report = _build_report(user_requirement, company_name, tool_args)
    if save_to_file:
        file_path = _save_report(report, file_path, company_name)
        return f"报告已生成并保存到: {file_path}"
    return report


def _build_report(user_requirement: str, company_name: str, tool_args: Dict[str, Any]) -> str:
    """构建完整报告"""
    # 生成报告时间
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 构建Markdown报告
    markdown_report = f"# {company_name} Financial Analysis Report\n\n"
    markdown_report += f"> Report Generated: {report_time}\n\n"
    
    # 损益表分析（由 LLM 生成）
    markdown_report += "## 📊 Income Statement Analysis\n\n"
    income_analysis = _chapter_analysis(user_requirement, tool_args, "income_basic", INCOME_ANALYSIS_PROMPT)
    markdown_report += f"{income_analysis}\n\n"
    
    # 资产负债表分析（由 LLM 生成）
    markdown_report += "## 📊 Balance Sheet Analysis\n\n"
    balance_analysis = _chapter_analysis(user_requirement, tool_args, "balance_basic", BALANCE_ANALYSIS_PROMPT)
    markdown_report += f"{balance_analysis}\n\n"
    
    # 现金流量表分析（由 LLM 生成）
    markdown_report += "## 📊 Cash Flow Analysis\n\n"
    cash_flow_analysis = _chapter_analysis(user_requirement, tool_args, "cashflow_basic", CASHFLOW_ANALYSIS_PROMPT)
    markdown_report += f"{cash_flow_analysis}\n\n"
    
    # 财务总结（由 LLM 生成）
    markdown_report += "## 📝 Financial Summary\n\n"
    financial_summary = _generate_financial_summary(company_name, income_analysis, balance_analysis, cash_flow_analysis)
    markdown_report += f"{financial_summary}\n\n"
    
    # 风险提示
    markdown_report += "## Investment Risk Disclaimer\n\n"
    markdown_report += "1. This report is for reference only and does not constitute investment advice\n"
    markdown_report += "2. Investment involves risks, please invest with caution\n"
    markdown_report += "3. It is recommended to make independent judgments based on multiple sources of information\n"
    markdown_report += "4. Past performance does not guarantee future results\n\n"
    
    markdown_report += "---\n"
    markdown_report += "*This report is automatically generated by FinAgent*"
    
    return markdown_report


def _analysis_company_name(user_requirement: str) -> str:
    from utils.utils import generate_text
    prompt_template = """
        User requirements: {user_requirement}
        Task: identify the target company that needs to generate a report in the user requirements, and only output the English standard name of the company (excluding other contents)
    """
    prompt = prompt_template.format(
        user_requirement=user_requirement
    )
    company_name = generate_text(prompt).strip()
    return company_name


def _param_analysis(user_requirement: str) -> Dict[str, Any]:
    from utils.utils import generate_text
    param_prompt_template = """
        SYSTEM_PROMPT: {system_prompt}
        User requirement: {user_requirement}
        Task: Generate JSON parameters for MCP tool invocation to retrieve stock data
        Requirements:
        - Return JSON format with MCP tool parameters
        - Include all required parameters
        - Ensure parameters are applicable to the given company

        Tool parameter definition:
        "company_performance": {{
            "description": "Retrieve comprehensive performance data for a specified company",
            "parameters": {{
                "ts_code": {{"type": "str", "description": "Stock code, e.g., '000001.SZ' for Ping An Bank, '600000.SH' for Pudong Development Bank"}},
                "start_date": {{"type": "str", "description": "Start date in YYYYMMDD format, e.g., '20230101'"}},
                "end_date": {{"type": "str", "description": "End date in YYYYMMDD format, e.g., '20231231'"}}
            }}
            "required": [
                "ts_code",
                "start_date",
                "end_date"
            ]
        }}

        Response format:
        {{
            "analysis": "Analysis process",
            "parameters": {{
                "parameter1_name": "parameter1_value",
                "parameter2_name": "parameter2_value"
            }}
        }}
    """
    param_prompt = param_prompt_template.format(
        system_prompt=SYSTEM_PROMPT,
        user_requirement=user_requirement
    )
    param = generate_text(param_prompt).strip()
    param = json.loads(param)
    tool_args = param.get("parameters", {})
    return tool_args


def _chapter_analysis(user_requirement: str, tool_args: Dict[str, Any], data_type: str, analysis_prompt_template: str) -> str:
    """分析损益表、资产负债表、现金流量表，都使用company_performance工具，只是prompt不同"""
    from utils.utils import generate_text, _call_tool_async
    tool_args["data_type"] = data_type
    raw_information = asyncio.run(_call_tool_async("company_performance", tool_args))
    prompt_template = analysis_prompt_template.format(
        system_prompt=SYSTEM_PROMPT,
        user_requirement=user_requirement,
        raw_information=raw_information
    )
    response = generate_text(prompt_template).strip()
    return response


def _generate_financial_summary(company_name: str, income_analysis: str, balance_analysis: str, cash_flow_analysis: str) -> str:
    """生成财务摘要"""
    prompt = f"""
        # SYSTEM_PROMPT: {SYSTEM_PROMPT}
        # company_name: {company_name}
        # income_analysis: {income_analysis}
        # balance_analysis: {balance_analysis}
        # cash_flow_analysis: {cash_flow_analysis}
        # Task: Synthesize the findings from the in-depth analysis of the income statement, balance sheet, and cash flow for the latest fiscal year. Highlight the core insights regarding the company's operational performance, financial stability, and cash management efficiency. Discuss the interrelations between revenue growth, cost management strategies, and their impact on profitability as revealed by the income statement. Incorporate the balance sheet's insights on financial structure, liquidity, and solvency to provide a comprehensive view of the company's financial health. Merge these with the cash flow analysis to illustrate the company's liquidity position, investment activities, and financing strategies. Conclude with a holistic assessment of the company's fiscal health, identifying strengths, potential risks, and strategic opportunities for growth and stability. Offer recommendations to address identified challenges and capitalize on the opportunities to enhance shareholder value in a single paragraph. The content must write in English.  Please keep your analysis concise, around 100-150 words, but don't show the word counts.
    """
    from utils.utils import generate_text
    summary = generate_text(prompt).strip()
    return summary


def _save_report(report_content: str, file_path: str = None, company_name: str = "") -> str:
    """
    保存报告到文件

    Args:
        report_content (str): 要保存的报告内容
        file_path (str): 指定的文件路径，如果为None则自动生成
        company_name (str): 公司名称，用于生成文件名

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
            safe_name = "".join(c for c in company_name[:20] if c.isalnum() or c in (' ', '-', '_'))
            safe_name = safe_name.replace(' ', '_') or "financial_report"
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