"""
创建日期：2026年02月11日
介绍：
"""
from typing import List, Dict, Any
import json

from config.loader import load_config
from llm.ollama_client import ollama_chat
from mcp_server import MCPServer

# 初始化配置和MCP服务器
config = load_config()
mcp_server = MCPServer()


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
    """调用Ollama模型生成文本"""
    messages = [{"role": "user", "content": prompt}]
    return ollama_chat(messages)


def call_mcp_tool(tool_name: str, args: Dict[str, Any]) -> str:
    """调用MCP工具并返回结果"""
    try:
        result = mcp_server.handle_tool_call(tool_name, args)
        return f"工具执行结果: {result['content']}"
    except Exception as e:
        return f"工具执行失败: {str(e)}"

