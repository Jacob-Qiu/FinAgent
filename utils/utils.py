"""
创建日期：2026年02月11日
介绍：
"""
from typing import List, Dict, Any
import json
import asyncio

from utils.config import load_config
from fastmcp import Client
from .mcp import get_local_mcp_client


config = load_config()
local_mcp_tools = {"add", "akshare_search", "generate_markdown_report", "retrieve_reports"}
qieman_mcp_tools = {"SearchFinancialNews"}
finmcp_mcp_tools = {"stock_data", "index_data"}



async def _call_tool_async(tool_name: str, args: Dict[str, Any]) -> str:
    """异步调用MCP工具，包含参数检查"""
    if tool_name in local_mcp_tools:
        # 本地 MCP 服务器调用工具
        local_mcp_client = get_local_mcp_client()
        async with local_mcp_client:
            result = await local_mcp_client.call_tool(tool_name, args)
            return result
    elif tool_name in qieman_mcp_tools:
        # 远程 且慢MCP 服务器调用工具
        MCP_URL = config["mcpServers"]["qieman"]
        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client

        async with sse_client(MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                response = await session.call_tool(tool_name, args)
                result = json.loads(response.content[0].text)
        return result
    elif tool_name in finmcp_mcp_tools:
        # 远程 FinanceMCP 服务器调用工具
        MCP_URL = config["mcpServers"]["finmcp"]
        from mcp.client.session import ClientSession
        from mcp.client.sse import sse_client
        async with sse_client(MCP_URL) as (read, write):
            async with ClientSession(read, write) as session:
                response = await session.call_tool(tool_name, args)
                result = response.content[0].text
        return result


def parse_plan(plan_content: str) -> List[str]:
    """
    解析 LLM 返回的计划内容，将其转换为结构化的步骤列表。

    参数:
        plan_content (str): LLM 生成的计划内容，通常是自然语言描述。

    返回:
        List[str]: 结构化的计划步骤列表。
    """
    # 假设计划内容是以换行符分隔的步骤
    steps = plan_content.strip().split("\n")

    # 过滤空行并去除编号（如 "1. xxx" 中的 "1. "）
    parsed_steps = []
    for step in steps:
        step = step.strip()
        if step:
            # 去除开头的数字和点号（如 "1. "）
            if ". " in step:
                step = step.split(". ", 1)[1]
            parsed_steps.append(step)

    return parsed_steps


def parse_tool_call(command: str) -> tuple[str, dict]:
    """
    解析工具调用命令，提取工具名称和参数。

    参数:
        command (str): 以 "TOOL:" 开头的命令字符串，格式如 "TOOL:tool_name {\"arg1\": value1, \"arg2\": value2}"

    返回:
        tuple[str, dict]: 工具名称和参数字典的元组。
    """
    # 去除 "TOOL:" 前缀并分割工具名称和参数部分
    _, tool_info = command.split(":", 1)
    tool_name, args_str = tool_info.strip().split(" ", 1)

    # 将参数字符串解析为字典
    try:
        args = json.loads(args_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON format in tool arguments: {args_str}") from e

    return tool_name, args


def generate_text(prompt: str) -> str:
    """调用LLM模型生成文本"""
    # 重新加载配置以获取最新的provider设置
    provider = config.get("llm_provider", "ollama")
    
    if provider == "gemini":
        from llm.gemini_client import gemini_chat
        return gemini_chat(prompt)
    else:
        # 默认使用Ollama
        from llm.ollama_client import ollama_chat
        messages = [{"role": "user", "content": prompt}]
        return ollama_chat(messages)




