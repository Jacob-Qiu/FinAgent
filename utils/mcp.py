"""
创建日期：2026年02月11日
介绍：MCP服务器和客户端管理器
"""
from fastmcp import FastMCP, Client
import yaml
import os

from .config import load_config
from tools.akshare_search import akshare_search as _akshare_search
from tools.calculator import add as _add
from tools.get_current_time import get_current_time as _get_current_time
from tools.generate_report import generate_markdown_report as _generate_markdown_report
from tools.report_retriever import retrieve_reports as _retrieve_reports

# 自定义MCP客户端
_local_mcp_client = None
_qieman_mcp_client = None


def create_local_mcp_server() -> FastMCP:
    """创建并配置FastMCP服务器"""
    mcp_local_server = FastMCP("FinAgent_local_MCP_Server")
    
    @mcp_local_server.tool()
    def add(add1: int, add2: int) -> str:
        result = _add(add1, add2)
        return str(result)
    
    @mcp_local_server.tool()
    def akshare_search(stock_code: str, data_type: str, start_date: str = None, end_date: str = None) -> str:
        if start_date and end_date:
            data = _akshare_search(stock_code, data_type, start_date, end_date)
        else:
            data = _akshare_search(stock_code, data_type)
        return str(data)
    
    @mcp_local_server.tool()
    def get_current_time(time_format: str = "standard") -> str:
        data = _get_current_time(time_format)
        return str(data)
    
    @mcp_local_server.tool()
    def generate_markdown_report(user_requirement: str, report_content: str) -> str:
        data = _generate_markdown_report(user_requirement, report_content, save_to_file=True)
        return str(data)
    
    @mcp_local_server.tool()
    def retrieve_reports(query: str, n_results: int = 5, filters: dict = None) -> str:
        data = _retrieve_reports(query, n_results, filters)
        return str(data)
    
    return mcp_local_server


def setup_local_mcp_client(server: FastMCP) -> Client:
    """创建并配置本地MCP客户端"""
    mcp_local_client = Client(server)
    global _local_mcp_client
    _local_mcp_client = mcp_local_client
    print("MCP服务器和客户端已初始化（In-memory模式）")
    
    return mcp_local_client


def get_local_mcp_client() -> Client:
    """获取全局本地MCP客户端"""
    global _local_mcp_client
    return _local_mcp_client


def setup_qieman_mcp_client() -> Client:
    """创建并配置qieman MCP客户端"""
    try:
        config = load_config()
        mcp_servers = config.get("mcpServers", {})
        qieman_url = mcp_servers.get("qieman")
        
        if not qieman_url:
            print("警告: config.yml 中未找到 qieman 配置")
            return None
        
        # 创建 qieman MCP 客户端
        # 使用 SSE 模式连接到远程服务器
        from mcp.client.sse import sse_client
        from mcp import ClientSession
        import asyncio
        
        async def create_qieman_client():
            async with sse_client(qieman_url) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    return session
        
        # 运行异步创建客户端
        qieman_client = asyncio.run(create_qieman_client())
        global _qieman_mcp_client
        _qieman_mcp_client = qieman_client
        print(f"Qieman MCP 客户端已初始化，连接到: {qieman_url}")
        
        return qieman_client
        
    except Exception as e:
        print(f"Qieman MCP 客户端初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_qieman_mcp_client() -> Client:
    """获取全局qieman MCP客户端"""
    global _qieman_mcp_client
    return _qieman_mcp_client


def setup_all_mcp_clients():
    """设置所有MCP客户端"""
    # 初始化本地MCP
    local_server = create_local_mcp_server()
    local_client = setup_local_mcp_client(local_server)
    
    # 初始化qieman MCP
    qieman_client = setup_qieman_mcp_client()
    
    return local_client, qieman_client
