"""
创建日期：2026年02月20日
介绍：分层记忆系统 - 实现工作记忆、情景记忆和长期记忆的管理
"""

from typing import Dict, List, Any, Optional, Tuple
import os
import json
from datetime import datetime, timedelta
import re
import sqlite3

# 尝试导入Chroma，如果没有安装则使用简单的相似度计算
try:
    import chromadb
    from chromadb.config import Settings
    has_chroma = True
    print("已加载Chroma向量数据库")
except ImportError:
    has_chroma = False
    print("警告: Chroma未安装，将使用简单的记忆存储")

# 尝试导入sentence-transformers，如果没有安装则使用简单的编码方式
try:
    from sentence_transformers import SentenceTransformer
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    has_embedding_model = True
except ImportError:
    has_embedding_model = False
    print("警告: sentence-transformers未安装，将使用简单的编码方式")

# 尝试导入rank_bm25进行混合检索
try:
    from rank_bm25 import BM25Okapi
    import nltk
    from nltk.tokenize import word_tokenize
    from nltk.corpus import stopwords
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    has_bm25 = True
    print("已加载BM25检索")
except ImportError:
    has_bm25 = False
    print("警告: rank_bm25未安装，将使用简单的文本匹配")

# 记忆存储路径
MEMORY_BASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "memories")
WORKING_MEMORY_PATH = os.path.join(MEMORY_BASE_PATH, "working")
EPISODIC_MEMORY_PATH = os.path.join(MEMORY_BASE_PATH, "episodic")
LONG_TERM_MEMORY_PATH = os.path.join(MEMORY_BASE_PATH, "long_term")
VECTOR_DB_PATH = os.path.join(MEMORY_BASE_PATH, "vector_db")

# 创建目录结构
def create_memory_directories():
    """创建记忆存储目录结构"""
    for path in [MEMORY_BASE_PATH, WORKING_MEMORY_PATH, EPISODIC_MEMORY_PATH, LONG_TERM_MEMORY_PATH, VECTOR_DB_PATH]:
        if not os.path.exists(path):
            os.makedirs(path)
            print(f"创建目录: {path}")

# 初始化目录结构
create_memory_directories()


class WorkingMemory:
    """工作记忆管理"""
    
    def __init__(self, capacity: int = 20):
        """
        初始化工作记忆
        
        Args:
            capacity: 工作记忆容量，默认存储最近20轮对话
        """
        self.capacity = capacity
        self.history = []  # 存储对话历史
        self.current_state = {}  # 存储当前状态
        self.temporary_context = {}  # 存储临时上下文
    
    def add_message(self, role: str, content: str):
        """
        添加消息到工作记忆
        
        Args:
            role: 消息角色，如 "user" 或 "assistant"
            content: 消息内容
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        
        self.history.append(message)
        
        # 保持记忆容量
        if len(self.history) > self.capacity:
            self.history = self.history[-self.capacity:]
    
    def update_state(self, state: Dict[str, Any]):
        """
        更新当前状态
        
        Args:
            state: 新的状态信息
        """
        self.current_state.update(state)
    
    def set_context(self, context: Dict[str, Any]):
        """
        设置临时上下文
        
        Args:
            context: 临时上下文信息
        """
        self.temporary_context = context
    
    def get_history(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        获取对话历史
        
        Args:
            limit: 返回的历史记录数量限制
            
        Returns:
            对话历史列表
        """
        if limit:
            return self.history[-limit:]
        return self.history
    
    def get_summary(self) -> str:
        """
        获取对话摘要
        
        Returns:
            对话摘要
        """
        if not self.history:
            return ""
        
        # 生成对话摘要
        summary = []
        for message in self.history:
            summary.append(f"{message['role']}: {message['content']}")
        
        return "\n".join(summary[-10:])  # 只包含最近10条
    
    def clear(self):
        """
        清空工作记忆
        """
        self.history = []
        self.current_state = {}
        self.temporary_context = {}


class EpisodicMemory:
    """情景记忆管理"""
    
    def __init__(self):
        """
        初始化情景记忆
        """
        self.episodic_path = EPISODIC_MEMORY_PATH
        self.vector_db_path = os.path.join(VECTOR_DB_PATH, "episodic_memory.db")
        self._init_vector_db()
    
    def _init_vector_db(self):
        """
        初始化SQLite向量数据库
        """
        conn = sqlite3.connect(self.vector_db_path)
        cursor = conn.cursor()
        
        # 创建表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS memory_embeddings (
            id TEXT PRIMARY KEY,
            content TEXT,
            metadata TEXT,
            timestamp TEXT,
            embedding BLOB
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_today_file_path(self) -> str:
        """
        获取今天的情景记忆文件路径
        
        Returns:
            今天的情景记忆文件路径
        """
        today = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.episodic_path, f"{today}.md")
    
    def save_episodic_memory(self, content: str, metadata: Dict[str, Any] = None):
        """
        保存情景记忆到文件
        
        Args:
            content: 记忆内容
            metadata: 元数据
        """
        if metadata is None:
            metadata = {}
        
        file_path = self.get_today_file_path()
        timestamp = datetime.now().isoformat()
        
        # 构建记忆条目
        memory_entry = f"""
## 记忆条目
- 时间: {timestamp}
- 元数据: {json.dumps(metadata, ensure_ascii=False)}
- 内容:
{content}

"""
        
        # 追加到文件
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(memory_entry)
        
        # 向量化并存储到SQLite
        self._store_embedding(content, metadata, timestamp)
        
        print(f"情景记忆已保存到: {file_path}")
    
    def _store_embedding(self, content: str, metadata: Dict[str, Any], timestamp: str):
        """
        存储向量化的记忆到SQLite
        
        Args:
            content: 记忆内容
            metadata: 元数据
            timestamp: 时间戳
        """
        if not has_embedding_model:
            return
        
        try:
            # 生成嵌入
            embedding = embedding_model.encode(content)
            embedding_blob = embedding.tobytes()
            
            # 存储到SQLite
            conn = sqlite3.connect(self.vector_db_path)
            cursor = conn.cursor()
            
            memory_id = f"episodic_{timestamp.replace(':', '-')}"
            cursor.execute(
                "INSERT OR REPLACE INTO memory_embeddings (id, content, metadata, timestamp, embedding) VALUES (?, ?, ?, ?, ?)",
                (memory_id, content, json.dumps(metadata), timestamp, embedding_blob)
            )
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"存储嵌入失败: {e}")
    
    def load_recent_memories(self, days: int = 2) -> List[str]:
        """
        加载最近几天的情景记忆
        
        Args:
            days: 要加载的天数
            
        Returns:
            最近几天的记忆内容列表
        """
        memories = []
        
        for i in range(days):
            target_date = datetime.now() - timedelta(days=i)
            date_str = target_date.strftime("%Y-%m-%d")
            file_path = os.path.join(self.episodic_path, f"{date_str}.md")
            
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        memories.append(content)
                    print(f"已加载 {date_str} 的情景记忆")
                except Exception as e:
                    print(f"加载 {date_str} 的情景记忆失败: {e}")
        
        return memories
    
    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        搜索相关的情景记忆
        
        Args:
            query: 搜索查询
            top_k: 返回的结果数量
            
        Returns:
            相关记忆列表，每个元素包含记忆内容和相似度得分
        """
        results = []
        
        # 首先使用BM25检索
        if has_bm25:
            bm25_results = self._search_bm25(query, top_k)
            results.extend(bm25_results)
        
        # 然后使用向量检索
        if has_embedding_model:
            vector_results = self._search_vector(query, top_k)
            results.extend(vector_results)
        
        # 去重并排序
        unique_results = {}
        for content, score in results:
            if content not in unique_results or score > unique_results[content]:
                unique_results[content] = score
        
        sorted_results = sorted(unique_results.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]
    
    def _search_bm25(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        使用BM25搜索
        
        Args:
            query: 搜索查询
            top_k: 返回的结果数量
            
        Returns:
            相关记忆列表
        """
        # 读取所有情景记忆文件
        memory_contents = []
        for filename in os.listdir(self.episodic_path):
            if filename.endswith('.md'):
                file_path = os.path.join(self.episodic_path, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        # 分割为记忆条目
                        entries = re.split(r'## 记忆条目', content)
                        for entry in entries:
                            if entry.strip():
                                memory_contents.append(entry.strip())
                except Exception as e:
                    print(f"读取 {filename} 失败: {e}")
        
        if not memory_contents:
            return []
        
        # 预处理文本
        stop_words = set()
        if has_bm25:
            try:
                stop_words = set(stopwords.words('chinese') + stopwords.words('english'))
            except:
                pass
        
        tokenized_corpus = []
        for content in memory_contents:
            tokens = []
            if has_bm25:
                try:
                    tokens = word_tokenize(content.lower())
                    tokens = [token for token in tokens if token not in stop_words and token.isalnum()]
                except:
                    pass
            tokenized_corpus.append(tokens)
        
        # 构建BM25模型
        bm25 = None
        if has_bm25 and tokenized_corpus:
            try:
                bm25 = BM25Okapi(tokenized_corpus)
            except:
                pass
        
        # 搜索
        results = []
        if bm25:
            try:
                query_tokens = []
                if has_bm25:
                    try:
                        query_tokens = word_tokenize(query.lower())
                        query_tokens = [token for token in query_tokens if token not in stop_words and token.isalnum()]
                    except:
                        pass
                scores = bm25.get_scores(query_tokens)
                
                # 排序并返回结果
                for i, score in enumerate(scores):
                    if score > 0:
                        results.append((memory_contents[i], score))
            except Exception as e:
                print(f"BM25搜索失败: {e}")
        
        # 如果BM25失败，使用简单文本匹配
        if not results:
            for content in memory_contents:
                similarity = 0.0
                if query.lower() in content.lower():
                    similarity = 0.8
                elif any(keyword in content.lower() for keyword in query.lower().split()):
                    similarity = 0.5
                
                if similarity > 0:
                    results.append((content, similarity))
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def _search_vector(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        使用向量搜索
        
        Args:
            query: 搜索查询
            top_k: 返回的结果数量
            
        Returns:
            相关记忆列表
        """
        results = []
        
        try:
            # 生成查询向量
            if not has_embedding_model:
                return results
            
            query_embedding = embedding_model.encode(query)
            
            # 从SQLite读取所有嵌入
            conn = sqlite3.connect(self.vector_db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT content, embedding FROM memory_embeddings")
            rows = cursor.fetchall()
            conn.close()
            
            # 计算相似度
            import numpy as np
            for content, embedding_blob in rows:
                if embedding_blob:
                    try:
                        stored_embedding = np.frombuffer(embedding_blob, dtype=np.float32)
                        similarity = np.dot(query_embedding, stored_embedding) / (
                            np.linalg.norm(query_embedding) * np.linalg.norm(stored_embedding)
                        )
                        if similarity > 0.5:  # 阈值
                            results.append((content, similarity))
                    except Exception as e:
                        print(f"计算相似度失败: {e}")
        except Exception as e:
            print(f"向量搜索失败: {e}")
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


class LongTermMemory:
    """长期记忆管理"""
    
    def __init__(self):
        """
        初始化长期记忆
        """
        self.long_term_path = LONG_TERM_MEMORY_PATH
        self._ensure_category_files()
    
    def _ensure_category_files(self):
        """
        确保分类文件存在
        """
        categories = [
            "financial_knowledge.md",
            "company_analysis.md",
            "investment_strategy.md",
            "market_trends.md"
        ]
        
        for category in categories:
            file_path = os.path.join(self.long_term_path, category)
            if not os.path.exists(file_path):
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"# {category.replace('.md', '')}\n\n")
                print(f"创建分类文件: {category}")
    
    def add_memory(self, content: str, category: str = "financial_knowledge", metadata: Dict[str, Any] = None):
        """
        添加记忆到长期记忆
        
        Args:
            content: 记忆内容
            category: 分类
            metadata: 元数据
        """
        if metadata is None:
            metadata = {}
        
        file_path = os.path.join(self.long_term_path, f"{category}.md")
        timestamp = datetime.now().isoformat()
        
        # 构建记忆条目
        memory_entry = f"""
## 记忆条目
- 时间: {timestamp}
- 元数据: {json.dumps(metadata, ensure_ascii=False)}
- 内容:
{content}

"""
        
        # 追加到文件
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(memory_entry)
        
        print(f"长期记忆已保存到: {file_path}")
    
    def search(self, query: str, category: str = None, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        搜索长期记忆
        
        Args:
            query: 搜索查询
            category: 分类过滤
            top_k: 返回的结果数量
            
        Returns:
            相关记忆列表
        """
        results = []
        
        # 确定要搜索的文件
        files_to_search = []
        if category:
            file_path = os.path.join(self.long_term_path, f"{category}.md")
            if os.path.exists(file_path):
                files_to_search.append(file_path)
        else:
            for filename in os.listdir(self.long_term_path):
                if filename.endswith('.md'):
                    files_to_search.append(os.path.join(self.long_term_path, filename))
        
        # 搜索每个文件
        for file_path in files_to_search:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # 分割为记忆条目
                    entries = re.split(r'## 记忆条目', content)
                    for entry in entries:
                        if entry.strip():
                            # 简单的文本匹配
                            similarity = 0.0
                            if query.lower() in entry.lower():
                                similarity = 0.8
                            elif any(keyword in entry.lower() for keyword in query.lower().split()):
                                similarity = 0.5
                            
                            if similarity > 0:
                                results.append((entry.strip(), similarity))
            except Exception as e:
                print(f"搜索 {file_path} 失败: {e}")
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]


class MemoryManager:
    """记忆管理器 - 协调工作记忆、情景记忆和长期记忆"""
    
    def __init__(self, working_memory_capacity: int = 20):
        """
        初始化记忆管理器
        
        Args:
            working_memory_capacity: 工作记忆容量
        """
        self.working = WorkingMemory(working_memory_capacity)
        self.episodic = EpisodicMemory()
        self.long_term = LongTermMemory()
        
        # 自动加载最近两天的情景记忆
        self._load_recent_episodic_memories()
    
    def _load_recent_episodic_memories(self):
        """
        加载最近两天的情景记忆
        """
        print("正在加载最近两天的情景记忆...")
        recent_memories = self.episodic.load_recent_memories(days=2)
        
        # 将最近的记忆添加到工作记忆作为上下文
        for memory in recent_memories:
            # 提取最后几条记忆条目
            entries = re.split(r'## 记忆条目', memory)
            recent_entries = entries[-3:]  # 只取最近3条
            
            for entry in recent_entries:
                if entry.strip():
                    # 简单处理，将记忆内容添加为系统消息
                    self.working.add_message("system", f"历史记忆: {entry.strip()[:500]}...")
    
    def add_message(self, role: str, content: str):
        """
        添加消息到工作记忆
        
        Args:
            role: 消息角色
            content: 消息内容
        """
        self.working.add_message(role, content)
    
    def update_state(self, state: Dict[str, Any]):
        """
        更新当前状态
        
        Args:
            state: 状态信息
        """
        self.working.update_state(state)
    
    def set_context(self, context: Dict[str, Any]):
        """
        设置临时上下文
        
        Args:
            context: 上下文信息
        """
        self.working.set_context(context)
    
    def save_episodic_memory(self):
        """
        保存当前工作记忆到情景记忆
        """
        summary = self.working.get_summary()
        if summary:
            metadata = {
                "type": "conversation_summary",
                "message_count": len(self.working.get_history()),
                "timestamp": datetime.now().isoformat()
            }
            self.episodic.save_episodic_memory(summary, metadata)
    
    def refine_long_term_memory(self, query: str = None):
        """
        从情景记忆中提炼长期记忆
        
        Args:
            query: 提炼的主题
        """
        # 搜索相关的情景记忆
        if query:
            relevant_memories = self.episodic.search(query, top_k=3)
        else:
            # 搜索最近的情景记忆
            recent_memories = self.episodic.load_recent_memories(days=1)
            relevant_memories = [(memory, 1.0) for memory in recent_memories]
        
        if relevant_memories:
            # 提炼关键信息
            for content, score in relevant_memories:
                # 简单的提炼逻辑，实际应用中可以使用LLM
                if score > 0.7:
                    # 确定分类
                    category = "financial_knowledge"
                    if "公司" in content or "分析" in content:
                        category = "company_analysis"
                    elif "投资" in content or "策略" in content:
                        category = "investment_strategy"
                    elif "市场" in content or "趋势" in content:
                        category = "market_trends"
                    
                    # 添加到长期记忆
                    self.long_term.add_memory(content, category)
    
    def retrieve_relevant_memories(self, query: str, top_k: int = 3) -> List[str]:
        """
        检索相关的记忆
        
        Args:
            query: 检索查询
            top_k: 返回的结果数量
            
        Returns:
            相关记忆列表
        """
        results = []
        
        # 搜索情景记忆
        episodic_results = self.episodic.search(query, top_k=top_k)
        results.extend([content for content, _ in episodic_results])
        
        # 搜索长期记忆
        long_term_results = self.long_term.search(query, top_k=top_k)
        results.extend([content for content, _ in long_term_results])
        
        # 去重并返回
        unique_results = []
        seen = set()
        for result in results:
            if result not in seen:
                seen.add(result)
                unique_results.append(result)
        
        return unique_results[:top_k]
    
    def get_combined_context(self, query: str = "", include_relevant: bool = True) -> str:
        """
        获取组合上下文（工作记忆 + 相关记忆）
        
        Args:
            query: 当前查询
            include_relevant: 是否包含相关的记忆
            
        Returns:
            组合上下文
        """
        # 获取工作记忆摘要
        working_context = self.working.get_summary()
        
        if include_relevant and query:
            # 检索相关的记忆
            relevant_memories = self.retrieve_relevant_memories(query)
            
            # 构建相关记忆上下文
            relevant_context = ""
            if relevant_memories:
                relevant_context = "\n## 相关历史信息\n"
                for i, memory in enumerate(relevant_memories, 1):
                    relevant_context += f"### 记忆 {i}\n"
                    relevant_context += f"{memory[:500]}...\n"  # 截断长记忆
                    relevant_context += "\n"
            
            # 组合上下文
            combined_context = working_context + relevant_context
        else:
            combined_context = working_context
        
        return combined_context
    
    def clear_working_memory(self):
        """
        清空工作记忆
        """
        self.working.clear()
    
    def get_history(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        获取对话历史
        
        Args:
            limit: 返回的历史记录数量限制
            
        Returns:
            对话历史列表
        """
        return self.working.get_history(limit)
    
    def get_summary(self) -> str:
        """
        获取对话摘要
        
        Returns:
            对话摘要
        """
        return self.working.get_summary()


# 全局记忆管理器实例
memory_manager = MemoryManager()

# 兼容旧的API接口
history = []
summary = ""

def update_summary(model: str):
    """
    更新对话摘要（兼容旧API）
    
    Args:
        model: 使用的语言模型名称
    """
    global summary
    
    # 从记忆管理器获取摘要
    summary = memory_manager.get_summary()
    
    # 将历史记录同步到全局变量
    global history
    history = memory_manager.get_history()
    
    print(f"[{model}] Summary updated: {summary}")


# 新的API接口
def add_message(role: str, content: str):
    """
    添加消息到记忆系统
    
    Args:
        role: 消息角色
        content: 消息内容
    """
    memory_manager.add_message(role, content)
    
    # 同步到全局变量
    global history
    history = memory_manager.get_history()


def get_relevant_memories(query: str, top_k: int = 3) -> List[str]:
    """
    获取相关的历史记忆
    
    Args:
        query: 查询文本
        top_k: 返回的结果数量
        
    Returns:
        相关记忆列表
    """
    return memory_manager.retrieve_relevant_memories(query, top_k)


def get_context(query: str = "", include_relevant: bool = True) -> str:
    """
    获取当前上下文（包括工作记忆和相关记忆）
    
    Args:
        query: 查询文本，用于检索相关记忆
        include_relevant: 是否包含相关的记忆
        
    Returns:
        上下文文本
    """
    return memory_manager.get_combined_context(query, include_relevant)


def save_episodic_memory():
    """
    保存当前工作记忆到情景记忆
    """
    memory_manager.save_episodic_memory()


def refine_long_term_memory(query: str = None):
    """
    从情景记忆中提炼长期记忆
    
    Args:
        query: 提炼的主题
    """
    memory_manager.refine_long_term_memory(query)


def clear_working_memory():
    """
    清空工作记忆
    """
    memory_manager.clear_working_memory()


def get_history(limit: int = None) -> List[Dict[str, Any]]:
    """
    获取对话历史
    
    Args:
        limit: 返回的历史记录数量限制
        
    Returns:
        对话历史列表
    """
    return memory_manager.get_history(limit)


def get_summary() -> str:
    """
    获取对话摘要
    
    Returns:
        对话摘要
    """
    return memory_manager.get_summary()


def transfer_memory():
    """
    转移记忆（从工作记忆到情景记忆，再到长期记忆）
    """
    # 保存到情景记忆
    save_episodic_memory()
    
    # 提炼到长期记忆
    refine_long_term_memory()