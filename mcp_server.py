"""
创建日期：2026年02月11日
介绍：MCP服务端
"""

# mcp_server.py
from typing import Dict, Any


from tools.calculator import add


class MCPServer:
    """
    MCP Server:
    - 对 Agent 暴露 tools / resources
    - 控制访问边界
    """

    def __init__(self):
        self.tools = {
            "add": self.add
        }

    # ===== Tool definitions =====

    def add(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Tool: 相加
        """
        adds = args["add_param"]
        data = add(adds[0], adds[1])
        return {
            "type": "tool_result",
            "tool": "add",
            "content": data
        }

    # def retrieve_reports(self, args: Dict[str, Any]) -> Dict[str, Any]:
    #     """
    #     Tool: RAG 研报检索
    #     """
    #     query = args["query"]
    #     docs = retrieve_reports(query)
    #     return {
    #         "type": "tool_result",
    #         "tool": "retrieve_reports",
    #         "content": docs
    #     }

    # ===== MCP dispatch =====

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any]):
        if tool_name not in self.tools:
            raise ValueError(f"Tool {tool_name} not registered")
        return self.tools[tool_name](args)

