"""
创建日期：2026年02月11日
介绍：MCP服务端
"""

# mcp_server.py
from typing import Dict, Any

from tools.akshare_search import akshare_search
from tools.calculator import add
from tools.get_current_time import get_current_time
from tools.generate_report import generate_markdown_report


class MCPServer:
    """
    MCP Server:
    - 对 Agent 暴露 tools / resources
    - 控制访问边界
    """

    def __init__(self):
        self.tools = {
            "add": self.add,
            "akshare_search": self.akshare_search,
            "get_current_time": self.get_current_time,
            "generate_markdown_report": self.generate_markdown_report
        }

    # ===== Tool definitions =====

    def add(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tool: 相加
        """
        add0 = args["add1"]
        add1 = args["add2"]
        data = add(add0, add1)
        return {
            "type": "tool_result",
            "tool": "add",
            "content": data
        }

    def akshare_search(self, args: Dict[str, Any]) -> Dict[str, Any]:
        stock_code = args["stock_code"]
        data_type = args["data_type"]
        
        # 处理可选参数
        start_date = args.get("start_date")
        end_date = args.get("end_date")
        
        if start_date and end_date:
            data = akshare_search(stock_code, data_type, start_date, end_date)
        else:
            data = akshare_search(stock_code, data_type)
        return {
            "type": "tool_result",
            "tool": "akshare_search",
            "content": data
        }

    def get_current_time(self, args: Dict[str, Any]) -> Dict[str, Any]:
        data = get_current_time()
        return {
            "type": "tool_result",
            "tool": "get_current_time",
            "content": data
        }

    def generate_markdown_report(self, args: Dict[str, Any]) -> Dict[str, Any]:
        user_requirement = args["user_requirement"]
        report_content = args["report_content"]
        data = generate_markdown_report(user_requirement, report_content, save_to_file=True)
        return {
            "type": "tool_result",
            "tool": "generate_markdown_report",
            "content": data
        }

    # ===== MCP dispatch =====

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any]):
        if tool_name not in self.tools:
            raise ValueError(f"Tool {tool_name} not registered")
        return self.tools[tool_name](args)

