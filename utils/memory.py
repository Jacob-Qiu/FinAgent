"""
创建日期：2026年02月20日
介绍：分层记忆系统 - 实现短期记忆和长期记忆的管理（使用Chroma向量数据库）
"""

# todo 这里面有一些常量或者配置信息需要写出来
from typing import Dict, List, Any, Optional, Tuple
import os
import json
from datetime import datetime

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


class ShortTermMemory:
    """短期记忆管理"""
    
    def __init__(self, capacity: int = 20):
        """
        初始化短期记忆
        
        Args:
            capacity: 短期记忆容量，默认存储最近20轮对话
        """
        self.capacity = capacity
        self.history = []  # 存储对话历史
        self.current_state = {}  # 存储当前状态
        self.temporary_context = {}  # 存储临时上下文
    
    def add_message(self, role: str, content: str):
        """
        添加消息到短期记忆
        
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
        self.current_state.update(state)  # 字典内置方法，增量更新
    
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
        清空短期记忆
        """
        self.history = []
        self.current_state = {}
        self.temporary_context = {}


class LongTermMemory:
    """长期记忆管理（使用Chroma向量数据库）"""
    
    def __init__(self, storage_path: str = "chroma_memory"):
        """
        初始化长期记忆
            - 同时维护内存备用存储（ self.memories ）和 Chroma 持久化存储
                - 备用存储结构 ：列表，每个元素为一个字典，包含 content（文本内容）、metadata（元数据字典）、id（唯一标识符）、timestamp（创建时间）
                - 持久化存储结构：documents（原始文本内容）, metadatas=[{**metadata, "timestamp": memory["timestamp"]}], ids（唯一标识符）, embeddings（存储文本的向量表示）
            - Chroma 初始化 ：如果安装了 Chroma，调用 _init_chroma() 创建持久化客户端
            - 容错设计 ：即使 Chroma 不可用，也能通过内存存储保证基本功能
        
        Args:
            storage_path: Chroma存储路径
        """
        self.storage_path = storage_path
        self.memories = []  # 存储记忆对象（备用）
        self.chroma_client = None
        self.collection = None  # Chroma持久化存储集合
        
        # 初始化Chroma
        if has_chroma:
            self._init_chroma()
    
    def _init_chroma(self):
        """
        初始化Chroma客户端和集合
        """
        try:
            # 创建Chroma客户端
            self.chroma_client = chromadb.PersistentClient(
                path=self.storage_path,
                settings=Settings(
                    anonymized_telemetry=False
                )
            )
            
            # 创建或获取集合
            self.collection = self.chroma_client.get_or_create_collection(
                name="agent_memory",
                metadata={"description": "Agent长期记忆存储"}
            )
            
            print(f"Chroma初始化成功，存储路径: {self.storage_path}")
        except Exception as e:
            print(f"Chroma初始化失败: {e}")
            self.chroma_client = None
            self.collection = None
    
    def add_memory(self, content: str, metadata: Dict[str, Any] = None):
        """
        添加记忆到长期记忆
            - 记忆对象构建 ：将输入的 content 和 metadata 包装成完整的记忆对象
            - 唯一标识 ：自动生成包含时间戳的唯一 ID，确保每条记忆的唯一性
            - 时间追踪 ：自动添加时间戳，记录记忆的创建时间
            - 双路存储 ：同时存储到内存备用存储和 Chroma 持久化存储
        
        Args:
            content: 记忆内容
            metadata: 记忆元数据
        """
        if metadata is None:
            metadata = {}
        
        # 创建记忆对象
        memory = {
            "content": content,
            "metadata": metadata,
            "timestamp": datetime.now().isoformat(),
            "id": f"memory_{len(self.memories)}_{datetime.now().timestamp()}"
        }
        
        # 添加到内存存储（备用）
        self.memories.append(memory)
        
        # 添加到Chroma
        if has_chroma and self.collection:
            try:
                # 生成嵌入（如果有模型）
                embedding = None
                if has_embedding_model:
                    embedding = embedding_model.encode(content).tolist()
                
                # 添加到集合
                self.collection.add(
                    documents=[content],
                    metadatas=[{
                        **metadata,
                        "timestamp": memory["timestamp"]
                    }],
                    ids=[memory["id"]],
                    embeddings=[embedding] if embedding else None
                )
                
                print(f"记忆已添加到Chroma: {content[:100]}...")
            except Exception as e:
                print(f"添加到Chroma失败: {e}")
        else:
            # 如果没有Chroma，只存储到内存
            print(f"记忆已添加到内存存储: {content[:100]}...")
    
    def search(self, query: str, top_k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """
        搜索相关记忆
        
        Args:
            query: 搜索查询
            top_k: 返回的结果数量
            
        Returns:
            相关记忆列表，每个元素包含记忆对象和相似度得分
        """
        results = []
        
        # 使用Chroma搜索
        if has_chroma and self.collection:
            try:
                # 生成查询嵌入（如果有模型）
                query_embedding = None
                if has_embedding_model:
                    query_embedding = embedding_model.encode(query).tolist()
                
                # 搜索
                # 确保n_results至少为1
                n_results = min(top_k, len(self.memories)) if len(self.memories) > 0 else top_k
                n_results = max(n_results, 1)  # 确保至少为1
                
                chroma_results = self.collection.query(
                    query_texts=[query],
                    n_results=n_results,
                    include=["documents", "metadatas", "distances"]
                )
                
                # 处理结果
                for i in range(len(chroma_results["ids"][0])):
                    doc_id = chroma_results["ids"][0][i]
                    document = chroma_results["documents"][0][i]
                    metadata = chroma_results["metadatas"][0][i]
                    distance = chroma_results["distances"][0][i]
                    
                    # 转换距离为相似度（0-1）
                    similarity = 1.0 / (1.0 + distance)
                    
                    # 构建记忆对象
                    memory = {
                        "id": doc_id,
                        "content": document,
                        "metadata": metadata
                    }
                    
                    results.append((memory, similarity))
            except Exception as e:
                print(f"Chroma搜索失败: {e}")
                # 失败时使用备用方法
                results = self._search_fallback(query, top_k)
        else:
            # 使用备用搜索方法
            results = self._search_fallback(query, top_k)
        
        return results
    
    def _search_fallback(self, query: str, top_k: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """
        备用搜索方法（当Chroma不可用时）
        
        Args:
            query: 搜索查询
            top_k: 返回的结果数量
            
        Returns:
            相关记忆列表
        """
        results = []
        
        # 简单的文本匹配
        for memory in self.memories:
            # 计算简单的文本相似度（包含关系）
            similarity = 0.0
            if query.lower() in memory["content"].lower():
                similarity = 0.8
            elif any(keyword in memory["content"].lower() for keyword in query.lower().split()):
                similarity = 0.5
            
            if similarity > 0:
                results.append((memory, similarity))
        
        # 按相似度排序
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def get_all_memories(self) -> List[Dict[str, Any]]:
        """
        获取所有存储的长期记忆
        
        Returns:
            所有长期记忆的列表
        """
        memories = []
        
        # 从内存存储获取
        for memory in self.memories:
            memories.append({
                "id": memory["id"],
                "content": memory["content"],
                "metadata": memory["metadata"],
                "timestamp": memory["timestamp"]
            })
        
        # 如果有Chroma，尝试从Chroma获取（可能更完整）
        if has_chroma and self.collection:
            try:
                # 从Chroma获取所有文档
                chroma_results = self.collection.get()
                
                # 构建记忆列表
                chroma_memories = []
                for i, (doc, metadata, id_) in enumerate(zip(
                    chroma_results.get("documents", []),
                    chroma_results.get("metadatas", []),
                    chroma_results.get("ids", [])
                )):
                    chroma_memories.append({
                        "id": id_,
                        "content": doc,
                        "metadata": metadata,
                        "timestamp": metadata.get("timestamp", "N/A")
                    })
                
                # 如果Chroma数据更完整，使用Chroma数据
                if chroma_memories:
                    memories = chroma_memories
                    print(f"从Chroma获取到 {len(memories)} 条记忆")
                else:
                    print(f"从内存获取到 {len(memories)} 条记忆")
            except Exception as e:
                print(f"从Chroma获取记忆失败: {e}")
                print(f"从内存获取到 {len(memories)} 条记忆")
        else:
            print(f"从内存获取到 {len(memories)} 条记忆")
        
        return memories
    
    def show_all_memories(self):
        """
        显示所有存储的长期记忆（格式化输出）
        """
        memories = self.get_all_memories()
        
        if not memories:
            print("没有找到存储的记忆")
            return
        
        print("\n" + "=" * 80)
        print("存储的长期记忆")
        print("=" * 80)
        
        for i, memory in enumerate(memories, 1):
            print(f"\n{'-' * 60}")
            print(f"记忆 {i}")
            print(f"ID: {memory['id']}")
            print(f"时间: {memory['timestamp']}")
            print(f"内容: {memory['content'][:200]}..." if len(memory['content']) > 200 else f"内容: {memory['content']}")
            if memory['metadata']:
                print(f"元数据: {json.dumps(memory['metadata'], ensure_ascii=False)}")
        
        print("\n" + "=" * 80)
        print(f"总计: {len(memories)} 条记忆")
        print("=" * 80)


class MemoryManager:
    """记忆管理器 - 协调短期记忆和长期记忆"""
    
    def __init__(self, short_term_capacity: int = 20, storage_path: str = "chroma_memory"):
        """
        初始化记忆管理器
        
        Args:
            short_term_capacity: 短期记忆容量
            storage_path: 长期记忆存储路径
        """
        self.short_term = ShortTermMemory(short_term_capacity)
        self.long_term = LongTermMemory(storage_path)
    
    def add_message(self, role: str, content: str):
        """
        添加消息到短期记忆
        
        Args:
            role: 消息角色
            content: 消息内容
        """
        self.short_term.add_message(role, content)
    
    def update_state(self, state: Dict[str, Any]):
        """
        更新当前状态
        
        Args:
            state: 状态信息
        """
        self.short_term.update_state(state)
    
    def set_context(self, context: Dict[str, Any]):
        """
        设置临时上下文
        
        Args:
            context: 上下文信息
        """
        self.short_term.set_context(context)
    
    def transfer_to_long_term(self, threshold: float = 0.7):
        """
        将重要信息从短期记忆转移到长期记忆
        
        Args:
            threshold: 相似性阈值
        """
        # 分析短期记忆中的信息
        history = self.short_term.get_history()
        
        if len(history) >= 2:
            # 提取对话摘要
            summary = self.short_term.get_summary()
            
            # 检查是否已经存在相似的记忆
            existing_memories = self.long_term.search(summary, top_k=1)
            
            if not existing_memories or existing_memories[0][1] < threshold:
                # 添加新记忆
                metadata = {
                    "type": "conversation_summary",
                    "message_count": len(history),
                    "timestamp": datetime.now().isoformat()
                }
                self.long_term.add_memory(summary, metadata)
                print(f"记忆已转移到长期存储: {summary[:100]}...")
    
    def retrieve_relevant_memories(self, query: str, top_k: int = 3, filter_metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        检索相关的长期记忆
        
        Args:
            query: 检索查询
            top_k: 返回的结果数量
            filter_metadata: 元数据过滤条件
            
        Returns:
            相关记忆列表
        """
        results = self.long_term.search(query, top_k)
        
        # 如果有过滤条件，进一步过滤结果
        if filter_metadata:
            filtered_results = []
            for memory, score in results:
                match = True
                for key, value in filter_metadata.items():
                    if key not in memory["metadata"] or memory["metadata"][key] != value:
                        match = False
                        break
                if match:
                    filtered_results.append(memory)
            return filtered_results
        
        return [memory for memory, _ in results]
    
    def get_all_long_term_memories(self) -> List[Dict[str, Any]]:
        """
        获取所有长期记忆
        
        Returns:
            所有长期记忆的列表
        """
        return self.long_term.get_all_memories()
    
    def show_all_long_term_memories(self):
        """
        显示所有长期记忆
        """
        self.long_term.show_all_memories()
    
    def get_combined_context(self, query: str, include_relevant: bool = True, filter_metadata: Dict[str, Any] = None) -> str:
        """
        获取组合上下文（短期记忆 + 相关长期记忆）
        
        Args:
            query: 当前查询
            include_relevant: 是否包含相关的长期记忆
            filter_metadata: 元数据过滤条件
            
        Returns:
            组合上下文
        """
        # 获取短期记忆摘要
        short_term_context = self.short_term.get_summary()
        
        if include_relevant:
            # 检索相关的长期记忆
            relevant_memories = self.retrieve_relevant_memories(query, filter_metadata=filter_metadata)
            
            # 构建长期记忆上下文
            long_term_context = ""
            if relevant_memories:
                long_term_context = "\n## 相关历史信息\n"
                for i, memory in enumerate(relevant_memories, 1):
                    long_term_context += f"### 记忆 {i}\n"
                    long_term_context += f"{memory['content']}\n"
                    if memory['metadata']:
                        long_term_context += f"元数据: {json.dumps(memory['metadata'], ensure_ascii=False)}\n"
                    long_term_context += "\n"
            
            # 组合上下文
            combined_context = short_term_context + long_term_context
        else:
            combined_context = short_term_context
        
        return combined_context
    
    def clear_short_term(self):
        """
        清空短期记忆
        """
        self.short_term.clear()
    
    def get_history(self, limit: int = None) -> List[Dict[str, Any]]:
        """
        获取对话历史
        
        Args:
            limit: 返回的历史记录数量限制
            
        Returns:
            对话历史列表
        """
        return self.short_term.get_history(limit)
    
    def get_summary(self) -> str:
        """
        获取对话摘要
        
        Returns:
            对话摘要
        """
        return self.short_term.get_summary()


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


def get_relevant_memories(query: str, top_k: int = 3, filter_metadata: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    获取相关的历史记忆
    
    Args:
        query: 查询文本
        top_k: 返回的结果数量
        filter_metadata: 元数据过滤条件
        
    Returns:
        相关记忆列表
    """
    return memory_manager.retrieve_relevant_memories(query, top_k, filter_metadata)


def get_context(query: str = "", include_relevant: bool = True, filter_metadata: Dict[str, Any] = None) -> str:
    """
    获取当前上下文（包括短期记忆和相关长期记忆）
    
    Args:
        query: 查询文本，用于检索相关长期记忆
        include_relevant: 是否包含相关的长期记忆
        filter_metadata: 元数据过滤条件
        
    Returns:
        上下文文本
    """
    return memory_manager.get_combined_context(query, include_relevant, filter_metadata)


def transfer_memory():
    """
    将当前短期记忆转移到长期记忆
    """
    memory_manager.transfer_to_long_term()


def list_all_memories() -> List[Dict[str, Any]]:
    """
    列出所有存储的长期记忆
    
    Returns:
        所有长期记忆的列表
    """
    return memory_manager.long_term.get_all_memories()


def show_all_memories():
    """
    显示所有存储的长期记忆（格式化输出）
    """
    memory_manager.long_term.show_all_memories()
