"""
创建日期：2026年02月11日
介绍：Agent节点函数定义
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from click import Tuple

from .utils import generate_text, call_mcp_tool
# 在具体函数中动态导入，确保获取最新值
# from .summary import history, summary


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
    from .summary import history, summary
    
    prompt_template = """
        ## 要求
        基于用户需求和对话上下文，生成一个详细的执行计划，每个步骤包含：
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
                "action": "需要执行的操作"
                "tool": "需要调用的工具"
            }},
            {{
                "step": 2,
                "description": "步骤2描述",
                "action": "需要执行的操作"
                "tool": "需要调用的工具"
            }}
        ]
        
        ## 当前对话上下文: 
        {summary}
        
        ## 用户当前需求: 
        {user_input}
        
        ## tool_candidates: 
        ["add"]
    """

    # 格式化提示文本
    prompt_text = prompt_template.format(
        user_input=state.user_input,
        summary=summary
    )
    # 调用LLM生成计划
    content = generate_text(prompt_text)

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
                "action": "分析用户输入的需求内容"
            },
            {
                "step": 2,
                "description": "执行核心任务",
                "action": "根据需求执行主要操作"
            },
            {
                "step": 3,
                "description": "总结结果",
                "action": "总结执行结果并返回给用户"
            }
        ]

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

    # 如果计划中指定了工具，则调用大模型分析参数
    if tool_name and tool_name != "None":
        # todo 构造参数分析提示，补充新的工具，工具的参数名参考mcp_server.py
        prompt_template = """
            请分析以下任务需要调用工具"{tool_name}"时的具体参数。
            
            任务描述: {action}
            用户原始需求: {user_input}
            
            请根据任务描述和原始需求，分析出调用该工具所需的参数。
            工具参数限制：
                - add: {{"add_param": List[int]}}
            
            回答格式：
            {{
                "分析": "你的分析过程",
                "参数": {{
                    "参数名": "参数值"
                }}
            }}
        """
        
        # 调用大模型分析参数
        prompt_text = prompt_template.format(tool_name=tool_name, action=action, user_input=state.user_input)
        param_analysis = generate_text(prompt_text)
        
        try:
            import json
            analysis_result = json.loads(param_analysis)

            # tool_args: {"参数名1": "参数值1"， "参数名2": "参数值2"}
            tool_args = analysis_result.get("参数", {})
            
            # todo 验证参数格式，有点冗余
            if tool_name == "add":
                if "add_param" not in tool_args or not isinstance(tool_args["add_param"], List) or len(tool_args["add_param"]) != 2:
                    result = f"参数格式错误: add工具需要包含两个数字的adds的数组，当前参数: {tool_args}"
                else:
                    # 调用相应工具
                    result = call_mcp_tool(tool_name, tool_args)
            else:
                # 其他工具直接调用
                result = call_mcp_tool(tool_name, tool_args)
            
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


# Replan节点 - 根据执行结果重新生成计划
def replan_node(state: AgentState) -> Dict[str, Any]:
    """根据执行结果重新生成计划或生成最终答案（每步执行后检查）"""
    # 动态导入获取最新的history和summary
    from .summary import history, summary
    
    # 准备对话历史和摘要
    history_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history[-5:]])
    
    # 构造检查提示，让大模型判断是否需要继续执行或生成答案
    prompt_template = """
        基于当前执行情况，请判断下一步应该做什么：

        用户原始需求: {user_input}
        当前执行进度: {current_step}/{total_steps}
        已完成的执行结果: {execution_results}
        
        请选择最合适的选项：
        1. 继续执行下一个步骤
        2. 生成最终答案（如果已经满足用户需求）
        3. 重新规划计划（如果需要调整策略）
        
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
