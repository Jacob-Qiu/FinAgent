"""
创建日期：2026年02月11日
介绍：
"""
# utils/summary.py

# 全局变量：存储对话历史和摘要
history = []  # 存储每一步的对话内容
summary = ""  # 当前对话的摘要

def update_summary(model: str):
    # todo 设计长短期记忆
    """
    更新对话摘要。

    参数:
        model (str): 使用的语言模型名称（可选，用于日志记录）。
    """
    global summary
    # 简单策略：将最近几条历史记录拼接为摘要
    recent_history = history[-10:]  # 取最近k条记录
    summary = "\n".join([msg.get("content", "") for msg in recent_history])
    print(f"[{model}] Summary updated: {summary}")
