# llm/gemini_client.py
import google.genai as genai
from typing import List, Dict, Any, Union
from utils.config import load_config
import os

def gemini_chat(messages: Union[str, List[Dict[str, str]]]) -> str:
    """
    调用 Gemini 模型生成回复。
    参数 messages 可以是字符串提示词，也可以是消息列表 [{"role": "user", "content": "..."}]。
    """
    config = load_config()
    gemini_config = config.get("gemini", {})
    api_key = gemini_config.get("api_key")
    model_name = gemini_config.get("model", "gemini-2.0-flash")
    
    # 尝试从环境变量获取 API Key（如果配置文件中未设置或为默认值）
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        return "错误: 未配置 Gemini API Key。请在 config.yml 中设置 gemini.api_key 或设置环境变量 GEMINI_API_KEY。"
        
    try:
        client = genai.Client(api_key=api_key)
        
        # 构造 Prompt
        if isinstance(messages, str):
            prompt = messages
        elif isinstance(messages, list):
            # 简单地将消息列表转换为文本 Prompt
            # 注意：Gemini 也有 start_chat 模式，但为了兼容性暂且拼接
            prompt = ""
            for msg in messages:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                # 简单的角色标记
                if role == "user":
                    prompt += f"User: {content}\n"
                elif role == "assistant":
                    prompt += f"Model: {content}\n"
                else:
                    prompt += f"{role}: {content}\n"
        else:
            return "错误: 消息格式不正确"
            
        response = client.models.generate_content(
            model=model_name,
            contents=prompt
        )
        return response.text
        
    except Exception as e:
        return f"Gemini API 调用失败: {str(e)}"
