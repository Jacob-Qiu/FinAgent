# verify_planner.py
import sys
import os
import json

# 添加路径，确保能找到 utils 模块
sys.path.append(os.getcwd())

from utils.nodes import plan_node, AgentState

def run_test(user_input: str):
    print(f"\n--- 测试用户输入: {user_input} ---")
    initial_state = AgentState(
        user_input=user_input,
        current_plan=[],
        current_step=0,
        execution_results=[],
        completed=False,
        final_answer=None
    )
    
    new_state = plan_node(initial_state)
    plan = new_state["current_plan"]
    
    print("生成的计划:")
    for step in plan:
        print(json.dumps(step, indent=2, ensure_ascii=False))
        
    # 验证逻辑
    if "行业分析" in user_input or "公司研究" in user_input or "研报查询" in user_input or "宏观经济" in user_input:
        if not plan or plan[0].get("tool") != "retrieve_reports":
            print("验证失败: 行业/公司/研报/宏观分析类需求未在第一步调用 retrieve_reports")
            return False
        if "filters" in plan[0].get("tool_args", {}) and ("INDUSTRY" in plan[0]["tool_args"]["filters"].get("ticker", "") or "MACRO" in plan[0]["tool_args"]["filters"].get("ticker", "")):
            print("验证成功: retrieve_reports 的 filters 包含 ticker 过滤条件")
        else:
            print("验证警告: retrieve_reports 的 filters 未包含预期的 ticker 过滤条件")

    if "股价" in user_input or "财务指标" in user_input or "实时行情" in user_input or "历史数据" in user_input:
        found_akshare = False
        for step in plan:
            if step.get("tool") == "akshare_search":
                found_akshare = True
                break
        if not found_akshare:
            print("验证失败: 股价/财务指标类需求未调用 akshare_search")
            return False

    print("验证成功: 计划生成符合预期。")
    return True

if __name__ == "__main__":
    tests = [
        "请给我一份关于人工智能行业的最新研究报告。",
        "查询英伟达（NVDA）的实时股价。",
        "我想了解最新的宏观经济形势分析报告。",
        "帮我计算 123 + 456。", # 应该不调用工具，或者调用 add 工具
        "总结一下最近的财经新闻。" # 应该不调用工具
    ]
    
    all_passed = True
    for test_input in tests:
        if not run_test(test_input):
            all_passed = False
            
    if all_passed:
        print("\n所有测试用例均通过！")
    else:
        print("\n部分测试用例未通过，请检查。")
