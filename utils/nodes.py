"""
创建日期：2026年02月11日
介绍：Agent节点函数定义
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import asyncio

from click import Tuple

from .utils import generate_text, _call_tool_async

# 定义状态结构
@dataclass
class AgentState:
    user_input: str
    current_plan: List[Dict[str, str]]
    current_step: int
    execution_results: List[Dict[str, Any]]
    completed: bool
    final_answer: Optional[str]


# Plan节点 - 生成执行计划
def plan_node(state: AgentState) -> Dict[str, Any]:
    """生成执行计划"""
    # 动态导入获取最新的history和summary
    from .memory import history, summary


    # todo 定义可用的工具列表
    tool_candidates = [
        {"tool_name": "add", "description": "两数相加"},
        {"stock_data": "add", "description": "获取指定股票的历史行情数据"},
        {"SearchFinancialNews": "add", "description": "根据关键词和时间范围搜索财经资讯内容"},
        {"get_current_time": "add", "description": "获取当前时间工具"},
        {"generate_markdown_report": "add", "description": "生成Markdown报告工具"},
        {"retrieve_reports": "add", "description": "研报检索工具"},
    ]

    prompt_template = """
        ## 要求
        基于用户需求和对话上下文，生成一个详细的执行计划，每一步计划包含：
            1. 步骤编号
            2. 步骤描述
            3. 需要执行的操作
            4. 需要调用的工具
        对于每一步计划，需要判断是否需要调用工具：如果需要，则需要从tools_candidate中确定需要的工具名；若不需要，则输入None
        示例格式：
        [
            {{
                "step": 1,
                "description": "步骤1描述",
                "action": "需要执行的操作",
                "tool": "需要调用的工具",
            }},
            ...
        ]

        ## 当前对话上下文: 
        {summary}
        
        ## 用户当前需求: 
        {user_input}
        
        ## tool_candidates: 
        {tool_candidates}
    """

    # 格式化提示文本
    prompt_text = prompt_template.format(
        user_input=state.user_input,
        summary=summary,
        tool_candidates=tool_candidates
    )
    # 调用LLM生成计划
    content = generate_text(prompt_text)

    # 解析计划（实际项目中可能需要更复杂的解析）
    import json
    plan = json.loads(content)
    return {
        "current_plan": plan,
        "current_step": 0,
        "execution_results": [],
        "completed": False
    }


# 执行节点 - 执行计划的当前步骤
def execute_node(state: AgentState) -> Dict[str, Any]:
    """执行计划的当前步骤"""
    if state.current_step >= len(state.current_plan):
        # 所有步骤执行完毕，准备生成最终答案
        return {
            "completed": True
        }

    current_task = state.current_plan[state.current_step]
    action = current_task["action"]
    tool_name = current_task.get("tool", None)
    execution_summary = "\n".join([f"步骤{res['step']}: {res['result']}" for res in state.execution_results])
    print(f"执行结果：{execution_summary}\n")

    # 如果计划中指定了工具，则调用工具
    if tool_name and tool_name != "None":

        # "akshare_search": {{
        #     "description": "股票数据查询工具",
        #     "parameters": {{
        #         "stock_code": {{"type": "str", "description": "股票代码"}},
        #         "data_type": {{
        #             "type": "str",
        #             "description": "数据类型",
        #             "enum": [
        #                 {{"value": "realtime", "description": "实时行情（用户查询当前或最新行情时使用）"}},
        #                 {{"value": "history", "description": "历史数据（用户查询指定日期范围的历史行情时使用）"}},
        #                 {{"value": "info", "description": "基本信息（用户查询股票基本信息时使用）"}}
        #             ]
        #         }},
        #         "start_date": {{"type": "str", "description": "开始日期（可选，格式: YYYYMMDD）"}},
        #         "end_date": {{"type": "str", "description": "结束日期（可选，格式: YYYYMMDD）"}}
        #     }}
        # }},

        # todo 构造参数分析提示，补充新的工具，工具的参数名参考mcp_server.py
        # todo 后续考虑将工具参数定义写出来
        prompt_template = """
            ## 要求
            请分析以下任务需要调用工具"{tool_name}"时的具体参数。
            任务描述: {action}
            用户原始需求: {user_input}
            前序步骤执行结果: {execution_summary}

            请根据任务描述和原始需求，分析出调用该工具所需的参数。

            ## 工具参数定义：
            {{
                "add": {{
                    "description": "加法计算工具",
                    "parameters": {{
                        "add1": {{"type": "int", "description": "第一个加数"}},
                        "add2": {{"type": "int", "description": "第二个加数"}}
                    }}
                }},
                "stock_data": {{
                    "description": "获取指定股票的历史行情数据",
                    "parameters": {{
                        "code": {{"type": "str", "description": "股票代码，如'000001.SZ'表示平安银行(A股)，'AAPL'表示苹果(美股)，'00700.HK'表示腾讯(港股)，'USDCNH.FXCM'表示美元人民币(外汇)，'CU2501.SHF'表示铜期货，'159919.SZ'表示沪深300ETF(基金)，'204001.SH'表示GC001国债逆回购，'113008.SH'表示可转债，'10001313.SH'表示期权合约"}},
                        "market_type": {{
                            "type": "str", 
                            "description": "市场类型，选一个",
                            "enum": [
                                {{"value": "cn", "description": "A股"}},
                                {{"value": "us", "description": "美股"}},
                                {{"value": "hk", "description": "港股"}},
                                {{"value": "fx", "description": "外汇"}},
                                {{"value": "futures", "description": "期货"}},
                                {{"value": "fund", "description": "债券逆回购"}},
                                {{"value": "repo", "description": "基金"}},
                                {{"value": "convertible_bond", "description": "可转债"}},
                                {{"value": "options", "description": "期权"}},
                            ]
                        }},
                        "start_date": {{"type": "str", "description": "起始日期，格式为YYYYMMDD，如'20230101'（可选）"}},
                        "end_date": {{"type": "str", "description": "结束日期，格式为YYYYMMDD，如'20230131'（可选）"}},
                        "indicators": {{
                            "type": "str", 
                            "description": "需要计算的技术指标，多个指标用空格分隔。若使用指标则必须明确指定参数，例如：'macd(12,26,9) rsi(14) kdj(9,3,3) boll(20,2) ma(10)'",
                            "enum": [
                                {{"value": "macd", "description": "MACD指标"}},
                                {{"value": "rsi", "description": "相对强弱指标"}},
                                {{"value": "kdj", "description": "随机指标"}},
                                {{"value": "boll", "description": "布林带"}},
                                {{"value": "ma", "description": "均线指标"}}
                            ]
                        }}
                    }}
                }},
                "SearchFinancialNews": {{
                    "description": "根据关键词和时间范围搜索财经资讯内容",
                    "parameters": {{
                        "keyword": {{"type": "str", "description": "搜索关键词；示例：“股票”"}},
                        "startDate": {{"type": "int", "description": "搜索开始日期（YYYY-MM-DD）；示例：“2024-01-01”（可选）"}},
                        "endDate": {{"type": "dict", "description": "搜索结束日期（YYYY-MM-DD）；示例：“2024-03-20”（可选）"}},
                        "page": {{"type": "int", "description": "页码（可选，默认为1）"}},
                        "pageSize": {{"type": "int", "description": "每页数量（可选，默认为20）"}}
                    }}
                }},
                "get_current_time": {{
                    "description": "获取当前时间工具",
                    "parameters": {{}}
                }},
                "generate_markdown_report": {{
                    "description": "生成Markdown报告工具",
                    "parameters": {{
                        "user_requirement": {{"type": "str", "description": "用户需求"}},
                        "report_content": {{"type": "str", "description": "报告内容"}}
                    }}
                }},
                "retrieve_reports": {{
                    "description": "研报检索工具",
                    "parameters": {{
                        "query": {{"type": "str", "description": "用户查询文本"}},
                        "n_results": {{"type": "int", "description": "返回的研报数量（可选，默认为5）"}},
                        "filters": {{"type": "dict", "description": "元数据过滤条件（可选，例如 {{'ticker': 'NVDA'}}）"}}
                    }}
                }}
            }}
            
            ## 回答格式：
            {{
                "分析": "你的分析过程",
                "参数": {{
                    "参数1名称": "参数1值",
                    "参数2名称": "参数2值"
                }}
            }}
        """

        # 调用大模型分析参数
        prompt_text = prompt_template.format(
            tool_name=tool_name, 
            action=action, 
            user_input=state.user_input,
            execution_summary=execution_summary
        )
        param_analysis = generate_text(prompt_text)
        try:
            import json
            analysis_result = json.loads(param_analysis)
            print(f"====={analysis_result}")
            tool_args = analysis_result.get("参数", {})
            
            try:
                result = asyncio.run(_call_tool_async(tool_name, tool_args))
            except Exception as e:
                result = f"{tool_name}工具调用失败: {str(e)}"
            
        except json.JSONDecodeError as e:
            result = f"JSON解析失败: {str(e)}，原始响应: {param_analysis}"

        except Exception as e:
            result = f"参数分析失败: {str(e)}，原始响应: {param_analysis}"
    else:
        # 对于不需要工具的任务，直接执行
        result = f"任务执行: {action}"

    # 记录执行结果
    execution_result = {
        "step": current_task["step"],
        "description": current_task["description"],
        "action": current_task["action"],
        "result": result
    }

    new_results = state.execution_results.copy()
    new_results.append(execution_result)

    return {
        "execution_results": new_results,
        "current_step": state.current_step + 1
    }


def replan_node(state: AgentState) -> Dict[str, Any]:
    """根据执行结果重新生成计划或生成最终答案（每步执行后检查）"""
    # 动态导入获取最新的history和summary
    from .memory import history, summary
    
    # 准备对话历史和摘要
    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[-5:]])
    
    # 构造检查提示，让大模型判断是否需要继续执行或生成答案
    prompt_template = """
        基于当前执行情况，请判断下一步应该做什么：

        用户原始需求: {user_input}
        当前执行进度: {current_step}/{total_steps}
        已完成的执行结果: {execution_results}
        
        重要提示：
        - 如果还有未执行的步骤（当前步骤 < 总步骤数），必须选择"1"继续执行
        - 只有当所有步骤都执行完毕后，才能选择"2"生成最终答案
        - 如果当前步骤执行失败，才选择"3"重新规划
        
        请选择最合适的选项：
        1. 继续执行下一个步骤（当还有未执行的步骤时）
        2. 生成最终答案（只有当所有步骤都执行完毕后）
        3. 重新规划计划（如果当前步骤执行失败）
        
        请只回答数字1、2或3。
    """
    
    # 格式化提示文本
    execution_summary = "\n".join([f"步骤{res['step']}: {res['result']}" for res in state.execution_results])
    prompt_text = prompt_template.format(
        user_input=state.user_input,
        current_step=state.current_step,
        total_steps=len(state.current_plan),
        execution_results=execution_summary
    )
    
    # 调用大模型进行判断
    decision = generate_text(prompt_text).strip()
    
    print(f"  🤖 AI决策: {decision}")  # 调试输出
    
    # 根据决策采取行动
    if decision.startswith("2") or state.current_step >= len(state.current_plan):
        # 生成最终答案
        answer_prompt = """
            基于以下执行结果和用户原始需求，生成一个简洁明了的最终答案。
            
            用户原始需求: {user_input}
            执行结果: {execution_results}
            
            请根据执行结果，直接回答用户的问题。答案应该是具体的、有针对性的。
            
            只需输出最终答案，不需要解释过程。
        """
        
        answer_text = answer_prompt.format(
            user_input=state.user_input,
            execution_results=execution_summary
        )
        
        final_answer = generate_text(answer_text)
        
        return {
            "completed": True,
            "final_answer": final_answer.strip()
        }
    
    elif decision.startswith("3"):
        # 重新规划计划
        replan_prompt = """
        基于当前执行结果和对话历史，重新生成执行计划。

        对话历史:
        {history_text}
        
        当前对话摘要:
        {summary}
        
        原始用户需求: {user_input}
        当前执行计划: {current_plan}
        已执行步骤: {current_step}
        执行结果: {execution_results}
        
        请根据以上信息，重新生成一个执行计划，包含剩余需要执行的步骤。
        """
        
        replan_text = replan_prompt.format(
            user_input=state.user_input,
            current_plan=state.current_plan,
            current_step=state.current_step,
            execution_results=execution_summary,
            history_text=history_text,
            summary=summary
        )
        
        content = generate_text(replan_text)
        
        # 解析新计划
        import json
        try:
            new_plan = json.loads(content)
            return {
                "current_plan": new_plan,
                "current_step": 0  # 重置步骤计数
            }
        except:
            # 如果解析失败，保持原有计划
            pass
    
    # 默认情况下继续执行当前计划
    return {
        "current_plan": state.current_plan,
        "current_step": state.current_step
    }