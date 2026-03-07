"""
创建日期：2026年02月11日
介绍： LangGraph Agent（核心调度） - 实现 Plan and Execute 模式
"""

from typing import Dict, List, Any
from langgraph.graph import StateGraph, END
import tkinter as tk
from tkinter import messagebox, scrolledtext

from utils.nodes import AgentState, plan_node, execute_node, replan_node
from utils.memory import (
    history, summary, update_summary,
    add_message, transfer_memory, get_context
)
from utils.mcp import create_local_mcp_server, setup_local_mcp_client


# 主Agent类
class PlanExecuteAgent:
    def __init__(self):
        self.graph = self._build_graph()
    
    def _build_graph(self):
        """构建状态图"""
        # 创建状态图
        graph = StateGraph(AgentState)
        
        # 添加节点
        graph.add_node("plan", plan_node)
        graph.add_node("execute", execute_node)
        graph.add_node("replan", replan_node)
        
        # 设置第一个被调用的节点
        graph.set_entry_point("plan")
        
        # 定义条件边
        def should_continue(state: AgentState):
            if state.completed:
                return END
            # 每执行一步就进入replan检查
            if state.current_step < len(state.current_plan):
                # 执行一步后进入replan
                if state.current_step > 0:  # 不是第一步
                    return "replan"
                # 第一步执行完也要检查
                return "execute" if state.current_step == 0 else "replan"
            return "replan"
        
        graph.add_conditional_edges("plan", should_continue)
        graph.add_conditional_edges("execute", should_continue)
        graph.add_conditional_edges("replan", should_continue)
        
        # 编译图
        return graph.compile()
    
    def run(self, user_input: str) -> Dict[str, Any]:
        """运行Agent处理用户输入"""
        # 将用户输入添加到记忆系统
        add_message("user", user_input)
        
        # 获取相关上下文
        context = get_context(user_input)
        print(f"获取到的上下文:\n{context[:200]}...")
        
        initial_state = AgentState(
            user_input=user_input,
            current_plan=[],
            current_step=0,
            execution_results=[],
            completed=False,
            final_answer=None
        )
        
        print(f"\n{'='*50}")
        print(f"用户输入: {user_input}")
        print(f"{'='*50}")
        
        # 执行图并输出过程信息
        result = self._execute_with_console_output(initial_state)
        
        # 将AI回复添加到记忆系统
        # todo 现在设计的是只要是final answer就更新摘要和长期记忆
        if result.get('final_answer'):
            add_message("assistant", result['final_answer'])
            # 更新摘要
            update_summary("PlanExecuteAgent")
            # 转移到长期记忆
            transfer_memory()
        
        return result
    
    def _execute_with_console_output(self, initial_state: AgentState) -> Dict[str, Any]:
        """执行带有控制台输出的版本 - 实现标准Plan and Execute流程（每步执行后检查）"""
        current_state = initial_state
        step_count = 0
        
        # 第一步必须是plan
        print(f"\n--- 第 1 步: 执行 plan 节点 ---")
        result_dict = plan_node(current_state)
        current_state = self._update_state(current_state, result_dict)
        self._display_plan(current_state)
        step_count = 1
        
        # 主循环：执行execute -> replan -> execute -> replan ...
        while True:
            step_count += 1
            
            # 执行execute步骤
            print(f"\n--- 第 {step_count} 步: 执行 execute 节点 ---")
            result_dict = execute_node(current_state)
            current_state = self._update_state(current_state, result_dict)
            self._display_execution_result(current_state)
            
            step_count += 1
            
            # 立即执行replan检查
            print(f"\n--- 第 {step_count} 步: 执行 replan 节点 ---")
            result_dict = replan_node(current_state)
            current_state = self._update_state(current_state, result_dict)
            
            # 检查replan结果
            if current_state.final_answer:
                print(f"\n🎯 最终答案: {current_state.final_answer}")
                print(f"\n✅ 执行完成！总共执行了 {step_count} 步")
                break
            elif current_state.completed:
                print(f"\n✅ 执行完成！总共执行了 {step_count} 步")
                break
            else:
                self._display_replan_info(current_state)
                # 继续下一轮execute-replan循环
                continue
        
        # 返回最终结果
        return {
            'current_plan': current_state.current_plan,
            'current_step': current_state.current_step,
            'execution_results': current_state.execution_results,
            'completed': current_state.completed,
            'final_answer': current_state.final_answer
        }
    
    def _determine_next_action(self, state: AgentState) -> str:
        """确定下一步动作 - 确保正确的Plan and Execute流程"""
        if state.completed:
            return "END"
        
        # 如果还没有计划，先执行plan
        if not state.current_plan:
            return "plan"
        
        # 如果还有未执行的步骤，执行execute
        if state.current_step < len(state.current_plan):
            return "execute"
        
        # 如果所有步骤都执行完了，执行replan来生成最终答案
        return "replan"

    def _update_state(self, old_state: AgentState, updates: Dict) -> AgentState:
        """更新状态"""
        return AgentState(
            user_input=old_state.user_input,
            current_plan=updates.get('current_plan', old_state.current_plan),
            current_step=updates.get('current_step', old_state.current_step),
            execution_results=updates.get('execution_results', old_state.execution_results),
            completed=updates.get('completed', old_state.completed),
            final_answer=updates.get('final_answer', old_state.final_answer)
        )
    
    def _display_plan(self, state: AgentState):
        """显示计划信息"""
        print("📋 制定的执行计划:")
        for i, plan_item in enumerate(state.current_plan, 1):
            desc = plan_item.get('description', '无描述')
            action = plan_item.get('action', '无操作')
            tool = plan_item.get('tool', '无工具')
            print(f"  {i}. {desc}")
            print(f"     操作: {action}")
            print(f"     工具: {tool}")
    
    def _display_execution_result(self, state: AgentState):
        """显示执行结果"""
        if state.execution_results:
            latest_result = state.execution_results[-1]
            print("⚡ 执行结果:")
            print(f"  步骤: {latest_result.get('description', '未知步骤')}")
            print(f"  结果: {latest_result.get('result', '无结果')}")
            print(f"  进度: {state.current_step}/{len(state.current_plan)}")
    
    def _display_replan_info(self, state: AgentState):
        """显示重新规划信息"""
        print("🔄 重新规划中...")
        if state.current_plan and state.current_step < len(state.current_plan):
            remaining = len(state.current_plan) - state.current_step
            print(f"  剩余步骤: {remaining}")

    def start_conversation(self):
        """启动多轮对话界面"""
        # 创建主窗口
        root = tk.Tk()
        root.title("FinAgent 对话系统")
        root.geometry("800x600")
        
        # 创建聊天显示区域
        chat_display = scrolledtext.ScrolledText(root, wrap=tk.WORD, width=80, height=25)
        chat_display.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        chat_display.config(state=tk.DISABLED)
        
        # 创建输入框架
        input_frame = tk.Frame(root)
        input_frame.pack(padx=10, pady=5, fill=tk.X)
        
        # 创建输入框
        user_input = tk.Entry(input_frame, width=70)
        user_input.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        
        # 创建发送按钮
        def send_message():
            message = user_input.get().strip()
            if message:
                # 显示用户消息
                chat_display.config(state=tk.NORMAL)
                chat_display.insert(tk.END, f"用户: {message}\n\n")
                chat_display.config(state=tk.DISABLED)
                user_input.delete(0, tk.END)
                
                # 处理用户输入
                try:
                    result = self.run(message)
                    final_answer = result.get('final_answer', '抱歉，我没有理解您的问题。')
                    
                    # 显示AI回复
                    chat_display.config(state=tk.NORMAL)
                    chat_display.insert(tk.END, f"AI助手: {final_answer}\n\n")
                    chat_display.config(state=tk.DISABLED)
                    chat_display.see(tk.END)
                
                except Exception as e:
                    error_msg = f"处理请求时出现错误: {str(e)}"
                    chat_display.config(state=tk.NORMAL)
                    chat_display.insert(tk.END, f"系统: {error_msg}\n\n")
                    chat_display.config(state=tk.DISABLED)
                    messagebox.showerror("错误", error_msg)
        
        send_button = tk.Button(input_frame, text="发送", command=send_message)
        send_button.pack(side=tk.RIGHT, padx=5)
        
        # 绑定回车键
        user_input.bind('<Return>', lambda event: send_message())
        
        # 显示欢迎信息
        chat_display.config(state=tk.NORMAL)
        chat_display.insert(tk.END, "欢迎使用FinAgent对话系统！\n请输入您的问题开始对话。\n\n")
        chat_display.config(state=tk.DISABLED)
        
        # 启动GUI主循环
        root.mainloop()


# 主函数
if __name__ == "__main__":
    # 创建并配置MCP服务器和客户端
    mcp_server = create_local_mcp_server()
    setup_local_mcp_client(mcp_server)
    []
    agent = PlanExecuteAgent()
    
    # 启动多轮对话界面
    print("正在启动FinAgent对话系统...")
    agent.start_conversation()