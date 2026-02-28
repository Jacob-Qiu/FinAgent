"""
创建日期：2026年02月11日
介绍：Agent节点函数定义
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from click import Tuple

from .utils import generate_text, call_mcp_tool

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

    # 定义可用的工具列表
    tool_candidates = [
        "add", 
        "akshare_search", 
        "get_current_time", 
        "generate_markdown_report",
        "retrieve_reports"
    ]

    prompt_template = """
        ## 要求
        基于用户需求和对话上下文，生成一个详细的执行计划，每个步骤包含：
            1. 步骤编号
            2. 步骤描述
            3. 需要执行的操作
            4. 需要调用的工具 (从 tool_candidates 中选择，若不需要则为 None)
            5. 工具参数 (如果调用工具，则提供参数，格式为字典)

        **强制规则:**
        - 如果用户需求涉及“行业分析”、“公司研究”、“研报查询”等，计划的第一步必须调用 `retrieve_reports` 工具。
        - **重要：** 提取股票代码时，必须创建一个独立的、无工具调用的步骤，其描述应为“从研报中穷举提取所有提到的A股、美股、港股的股票代码和公司名称”，确保全面提取，不要遗漏。
        - 如果用户需求涉及“股价”、“财务指标”、“实时行情”、“历史数据”等，计划中必须调用 `akshare_search` 工具。
        - **关键规则：** 如果需要根据上一步的输出结果提取具体参数（例如从研报中提取股票代码），**必须**单独创建一个步骤进行提取（tool: null），然后再进行下一步工具调用。严禁在同一个步骤中既提取又查询！
        - **参数规则：** 如果工具参数的值依赖于前序步骤的输出（即在制定计划时未知），**严禁**在 `tool_args` 中填写猜测值或描述性文字（如 "步骤X的结果"）。必须将该参数留空，或者将整个 `tool_args` 设为 null，交由执行阶段动态分析。
        - 计划必须是逐步的，逻辑清晰，能够直接指导执行。

        示例格式：
        [
            {{
                "step": 1,
                "description": "步骤1描述",
                "action": "需要执行的操作",
                "tool": "需要调用的工具",
                "tool_args": {{"参数名1": "参数值1", "参数名2": "参数值2"}} # 如果有工具调用
            }},
            ...
        ]

        ## Few-shot Examples:

        ### 示例 1: 行业分析
        用户需求: "请给我一份关于人工智能行业的最新研究报告。"
        计划:
        [
            {{
                "step": 1,
                "description": "检索人工智能行业的最新研究报告",
                "action": "使用研报检索工具查询人工智能行业的最新报告",
                "tool": "retrieve_reports",
                "tool_args": {{"query": "人工智能行业最新研究报告", "filters": {{"ticker": "INDUSTRY"}}}}
            }},
            {{
                "step": 2,
                "description": "生成人工智能行业投资建议报告",
                "action": "根据检索到的报告内容，生成一份人工智能行业的投资建议报告",
                "tool": "generate_markdown_report",
                "tool_args": {{"user_requirement": "人工智能行业投资建议报告", "report_content": "步骤1的执行结果"}}
            }}
        ]

        ### 示例 2: 股票实时行情
        用户需求: "查询英伟达（NVDA）的实时股价。"
        计划:
        [
            {{
                "step": 1,
                "description": "查询英伟达（NVDA）的实时股价",
                "action": "使用股票数据查询工具获取英伟达的实时行情",
                "tool": "akshare_search",
                "tool_args": {{"stock_code": "NVDA", "data_type": "realtime"}}
            }},
            {{
                "step": 2,
                "description": "生成英伟达实时股价报告",
                "action": "根据查询到的实时股价，生成一份报告",
                "tool": "generate_markdown_report",
                "tool_args": {{"user_requirement": "英伟达实时股价报告", "report_content": "步骤1的执行结果"}}
            }}
        ]

        ### 示例 3: 宏观经济报告
        用户需求: "我想了解最新的宏观经济形势分析报告。"
        计划:
        [
            {{
                "step": 1,
                "description": "检索最新的宏观经济形势分析报告",
                "action": "使用研报检索工具查询最新的宏观经济报告",
                "tool": "retrieve_reports",
                "tool_args": {{"query": "最新宏观经济形势分析报告", "filters": {{"ticker": "MACRO"}}}}
            }},
            {{
                "step": 2,
                "description": "生成宏观经济分析报告",
                "action": "根据检索到的报告内容，生成一份宏观经济分析报告",
                "tool": "generate_markdown_report",
                "tool_args": {{"user_requirement": "宏观经济分析报告", "report_content": "步骤1的执行结果"}}
            }}
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

    # 清理 Markdown 标记
    content = clean_json_response(content)

    # 解析计划（实际项目中可能需要更复杂的解析）
    import json
    try:
        plan = json.loads(content)
    except:
        # 如果解析失败，生成一个默认计划
        plan = [
            {
                "step": 1,
                "description": "分析用户需求",
                "action": "分析用户输入的需求内容",
                "tool": None,
                "tool_args": {}
            },
            {
                "step": 2,
                "description": "执行核心任务",
                "action": "根据需求执行主要操作",
                "tool": None,
                "tool_args": {}
            },
            {
                "step": 3,
                "description": "总结结果",
                "action": "总结执行结果并返回给用户",
                "tool": None,
                "tool_args": {}
            }
        ]

    return {
        "current_plan": plan,
        "current_step": 0,
        "execution_results": [],
        "completed": False
    }


def clean_json_response(response: str) -> str:
    response = response.strip()
    # 处理可能的markdown代码块标记
    if response.startswith("```json"):
        response = response[7:]
    elif response.startswith("```"):
        response = response[3:]
    
    if response.endswith("```"):
        response = response[:-3]
        
    return response.strip()


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
    tool_args = current_task.get("tool_args", {})

    # 如果计划中指定了工具，则调用工具
    if tool_name and tool_name != "None":
        
        # 检查参数是否完整（是否存在None值）
        has_none_value = False
        if isinstance(tool_args, dict):
            for v in tool_args.values():
                if v is None:
                    has_none_value = True
                    break
        
        # 如果计划中已经提供了完整的 tool_args，则直接使用
        if tool_args and not has_none_value:
            final_tool_args = tool_args
        else:
            # 准备前序步骤的执行结果作为上下文
            execution_summary = "\n".join([f"步骤{res['step']}结果: {res['result']}" for res in state.execution_results])
            
            # 否则，调用大模型分析参数
            prompt_template = """
                请分析以下任务需要调用工具"{tool_name}"时的具体参数。
                
                任务描述: {action}
                用户原始需求: {user_input}
                
                前序步骤执行结果（上下文）:
                {execution_summary}
                
                请根据任务描述、原始需求和上下文，分析出调用该工具所需的参数。
                
                **重要规则:**
                1. 参数名称必须与工具参数定义中的key完全一致，严禁翻译或修改参数名！
                2. 如果前序步骤的结果为空或无法获取所需信息，**严禁虚构参数值**！请在"分析"字段中说明情况，并在"参数"中返回空值或不包含该参数。
                3. **穷举提取规则**: 如果参数值依赖于前序步骤的输出，**必须穷举提取所有符合条件的具体数据值**（例如，从研报中提取所有提到的股票 "NVDA, AMD, MSFT"），**严禁只提取一个或部分**，也**严禁使用** "步骤X的结果"、"上一步提取的代码" 等描述性文字！
                
                **特殊规则 for generate_markdown_report:**
                - 如果工具是 `generate_markdown_report`，它的 `report_content` 参数**必须**是一个综合了前面所有步骤执行结果的、详尽的、可直接阅读的字符串。**必须**将 `execution_summary` 中的所有信息（研报摘要、股票行情等）整合成一段通顺的文本。**严禁**在此处使用 "步骤1的结果" 或类似的占位符！

                **特殊规则 for akshare_search:**
                - `data_type` 参数必须且只能从 ['realtime', 'history', 'info'] 中三选一。
                - `stock_code` 支持多只股票，如果前序步骤提取了多个股票代码，请用逗号分隔（如 "NVDA, AAPL, MSFT"）。
                
                工具参数定义：
                {{
                    "add": {{
                        "description": "加法计算工具",
                        "parameters": {{
                            "add1": {{"type": "int", "description": "第一个加数"}},
                            "add2": {{"type": "int", "description": "第二个加数"}}
                        }}
                    }},
                    "akshare_search": {{
                        "description": "全能股票查询工具。支持中文名、A股代码、美港股代码。系统会自动识别市场并处理代码转换。支持多只股票（逗号分隔）。",
                        "parameters": {{
                            "stock_code": {{"type": "str", "description": "股票代码（支持单个或多个，多个用逗号分隔）"}},
                            "data_type": {{
                                "type": "str",
                                "description": "数据类型",
                                "enum": [
                                    {{"value": "realtime", "description": "实时行情（用户查询当前或最新行情时使用）"}},
                                    {{"value": "history", "description": "历史数据（用户查询指定日期范围的历史行情时使用）"}},
                                    {{"value": "info", "description": "基本信息（用户查询股票基本信息时使用）"}}
                                ]
                            }},
                            "start_date": {{"type": "str", "description": "开始日期（可选，格式: YYYYMMDD）"}},
                            "end_date": {{"type": "str", "description": "结束日期（可选，格式: YYYYMMDD）"}}
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
                            "report_content": {{"type": "str", "description": "报告内容，必须是根据前序步骤结果生成的详尽文本"}}
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
                
                回答格式（请严格遵守JSON格式）：
                {{
                    "分析": "你的分析过程（如果缺少必要信息，请在此说明）",
                    "参数": {{
                        "参数1名称": "参数1值",
                        "参数2名称": "参数2值"
                    }}
                }}

                示例1：
                {{
                    "分析": "从任务描述中提取到股票代码为NVDA，需要查询实时行情。",
                    "参数": {{
                        "stock_code": "NVDA",
                        "data_type": "realtime"
                    }}
                }}

                示例2（基于上下文）：
                上下文：步骤1结果：发现股票 NVDA 和 AMD。
                任务：查询这些股票行情。
                {{
                    "分析": "前序步骤发现了NVDA和AMD，需要查询它们的实时行情。",
                    "参数": {{
                        "stock_code": "NVDA, AMD",
                        "data_type": "realtime"
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
                # 清理 Markdown 标记
                param_analysis = clean_json_response(param_analysis)
                analysis_result = json.loads(param_analysis)
                extracted_tool_args = analysis_result.get("参数", {})

                # 参数名映射（容错处理，防止LLM翻译参数名）
                PARAM_MAPPING = {
                    "用户需求": "user_requirement",
                    "报告内容": "report_content",
                    "查询": "query",
                    "数量": "n_results",
                    "过滤条件": "filters",
                    "股票代码": "stock_code",
                    "数据类型": "data_type",
                    "开始日期": "start_date",
                    "结束日期": "end_date",
                    "加数1": "add1",
                    "加数2": "add2"
                }
                new_args = {}
                for k, v in extracted_tool_args.items():
                    if k in PARAM_MAPPING:
                        new_args[PARAM_MAPPING[k]] = v
                    else:
                        new_args[k] = v
                final_tool_args = new_args

            except json.JSONDecodeError as e:
                import traceback
                error_detail = traceback.format_exc()
                result = f"JSON解析失败: {str(e)}，原始响应: {param_analysis}"
                # 如果解析失败，直接返回错误，不尝试调用工具
                return {
                    "execution_results": state.execution_results + [{
                        "step": current_task["step"],
                        "description": current_task["description"],
                        "action": current_task["action"],
                        "result": result
                    }],
                    "current_step": state.current_step + 1
                }
            except Exception as e:
                import traceback
                error_detail = traceback.format_exc()
                result = f"参数分析失败: {str(e)}，原始响应: {param_analysis}"
                # 如果分析失败，直接返回错误，不尝试调用工具
                return {
                    "execution_results": state.execution_results + [{
                        "step": current_task["step"],
                        "description": current_task["description"],
                        "action": current_task["action"],
                        "result": result
                    }],
                    "current_step": state.current_step + 1
                }
        
        # 硬代码修复：防止 LLM 幻觉生成错误的 data_type
        if final_tool_args.get('data_type') in ['daily_history', 'stock_history']:
            final_tool_args['data_type'] = 'history'

        # 增加参数校验：防止将描述性文字作为参数传递
        # 常见幻觉关键词
        suspicious_keywords = ["提取", "列表", "步骤", "根据", "执行结果", "分析", "获取"]
        
        for key, value in final_tool_args.items():
            # 跳过特定字段
            if key in ["user_requirement", "report_content", "query"]:
                continue
                
            if isinstance(value, str):
                # 检查是否为空或None字符串
                if not value or value.lower() == "none":
                    error_msg = f"参数校验失败: 参数 '{key}' 的值为空。请检查前序步骤是否成功获取了数据。"
                    return {
                        "execution_results": state.execution_results + [{
                            "step": current_task["step"],
                            "description": current_task["description"],
                            "action": current_task["action"],
                            "result": error_msg
                        }],
                        "current_step": state.current_step + 1
                    }

                # 如果包含多个关键词或者长度异常且包含关键词
                if any(keyword in value for keyword in suspicious_keywords) and len(value) > 4:
                    # 再次确认不是合法的文件名或查询字符串（虽然query已跳过）
                    # 这里主要拦截像 "从步骤1的结果中提取股票代码" 这样的值
                    error_msg = f"参数校验失败: 参数 '{key}' 的值 '{value}' 似乎是描述性文字而非有效参数。请检查前序步骤是否成功获取了数据。"
                    return {
                        "execution_results": state.execution_results + [{
                            "step": current_task["step"],
                            "description": current_task["description"],
                            "action": current_task["action"],
                            "result": error_msg
                        }],
                        "current_step": state.current_step + 1
                    }

        try:
            result = call_mcp_tool(tool_name, final_tool_args)
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            result = f"{tool_name}工具调用失败: {str(e)}"
    else:
        # 对于不需要工具的任务，调用大模型根据上下文执行
        execution_summary = "\n".join([f"步骤{res['step']}结果: {res['result']}" for res in state.execution_results])
        
        prompt = f"""
        请根据上下文执行以下任务。
        
        任务描述: {action}
        用户原始需求: {state.user_input}
        
        前序步骤执行结果（上下文）:
        {execution_summary}
        
        请直接输出任务的执行结果。如果任务是提取信息，请直接列出提取到的信息。
        """
        try:
            result = generate_text(prompt)
        except Exception as e:
            result = f"任务执行失败: {str(e)}"

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


# Replan节点 - 根据执行结果重新生成计划
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
    
    # 自动检测关键错误并强制重规划
    last_result = state.execution_results[-1]["result"] if state.execution_results else ""
    if "未找到A股代码" in last_result or "无法识别该公司的股票代码" in last_result or "参数校验失败" in last_result or "未找到美股代码" in last_result or "未找到港股代码" in last_result:
        decision = "3"
        print(f"  ⚠️ 检测到关键错误，强制重规划")

    print(f"  🤖 AI决策: {decision}")  # 调试输出
    
    # 根据决策采取行动
    if decision.startswith("3"):
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
        
        **特别注意:**
        1. 如果执行结果显示任务失败（例如"未找到研报"、"参数校验失败"等），请必须修改计划！
        2. 如果研报检索结果为空，请尝试放宽检索条件（例如移除filters参数，或使用更通用的查询词）。
        3. 如果是因为参数错误导致失败，请重新尝试该步骤，但确保参数正确。
        4. **重要：** 如果前序步骤（如研报检索）获取到了具体的 A 股公司名单，必须在接下来的步骤中优先安排对这些 A 股公司的查询。优先验证研报里的 A 股逻辑，其次才是美股常识。
        5. **错误修复：** 如果上一步报错“未找到代码”或“无法识别”，请在新的计划中增加一个专门的步骤：先使用 akshare_search 的 info 模式或通过网络搜索获取该公司的准确 6 位股票代码，然后再查询行情。
        
        请根据以上信息，重新生成一个执行计划，包含剩余需要执行的步骤。
        
        回答格式（请严格遵守JSON格式）：
        [
            {{
                "step": 1,
                "description": "步骤描述",
                "action": "需要执行的操作",
                "tool": "工具名称",
                "tool_args": {{"参数名": "参数值"}}
            }},
            ...
        ]
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

    elif decision.startswith("2") or state.current_step >= len(state.current_plan):
        # 生成最终答案
        answer_prompt = """
            基于以下执行结果和用户原始需求，生成一个全面、详尽且专业的最终答案。
            
            用户原始需求: {user_input}
            执行结果: {execution_results}
            
            **回答规范:**
            1.  **引用来源**: 如果答案中包含了来自研报的信息，**必须**明确指出信息来源。例如：“根据中银国际于2025年10月发布的《“十五五”规划前瞻》报告显示...”。
            2.  **数据完整**: 确保所有从研报中提取的关键信息（如公司列表、核心观点）和查询到的数据（如股票行情）都包含在内。
            3.  **格式清晰**: 使用Markdown格式，使回答结构清晰、易于阅读。
            4.  **语言专业**: 使用专业的金融术语进行分析和总结。
            
            请根据以上规范，直接回答用户的问题，无需解释过程。
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

    # 默认情况下继续执行当前计划
    return {
        "current_plan": state.current_plan,
        "current_step": state.current_step
    }
