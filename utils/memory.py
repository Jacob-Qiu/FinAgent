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
from utils.utils import generate_text

# 按需加载 sentence-transformers，避免启动时就初始化嵌入模型
_embedding_model = None
_embedding_model_name = "paraphrase-multilingual-MiniLM-L12-v2"


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(_embedding_model_name)
        return _embedding_model
    except ImportError:
        print("警告: sentence-transformers未安装，将使用简单的编码方式")
        return None


def _encode_embedding(text: str):
    model = _get_embedding_model()
    if model is None:
        return None
    return model.encode(text)

# 尝试导入rank_bm25进行混合检索
try:
    from rank_bm25 import BM25Okapi
    # 使用jieba进行中文分词
    import jieba
    import jieba.analyse
    has_bm25 = True
    print("已加载BM25检索（使用jieba中文分词）")
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
        
        # 生成对话摘要（返回完整的工作记忆内容）
        summary = []
        for message in self.history:
            summary.append(f"{message['role']}: {message['content']}")
        
        return "\n".join(summary)  # 返回完整的工作记忆内容
    
    def get_recent_summary(self, message_count: int) -> str:
        """
        获取最近指定数量的消息摘要
        
        Args:
            message_count: 要获取的消息数量
            
        Returns:
            最近消息的摘要
        """
        if not self.history:
            return ""
        
        # 获取最近指定数量的消息
        recent_messages = self.history[-message_count:]
        summary = []
        for message in recent_messages:
            summary.append(f"{message['role']}: {message['content']}")
        
        return "\n".join(summary)
    
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
        try:
            # 生成嵌入
            embedding = _encode_embedding(content)
            if embedding is None:
                return
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
        
        # 日期格式标准化：将各种格式的日期统一为 YYYY-MM-DD
        normalized_query = self._normalize_date_format(query)
        
        # 首先使用BM25检索
        if has_bm25:
            bm25_results = self._search_bm25(normalized_query, top_k)
            results.extend(bm25_results)
        
        # 然后使用向量检索
        if _get_embedding_model() is not None:
            vector_results = self._search_vector(normalized_query, top_k)
            results.extend(vector_results)
        
        # 日期相关查询特殊处理：如果查询中包含日期关键词，增强相关记忆的得分
        date_patterns = [
            r'\d{4}[年\-\.]\d{1,2}[月\-\.]\d{1,2}[日]?',  # 2026.4.6, 2026-04-06, 2026年4月6日
            r'\d{4}年',  # 2026年
            r'\d{1,2}月\d{1,2}日',  # 4月6日
        ]
        has_date_query = any(re.search(pattern, query) for pattern in date_patterns)
        
        if has_date_query:
            # 对包含日期的结果增加权重
            for i, (content, score) in enumerate(results):
                # 检查内容中是否也包含日期
                if any(re.search(pattern, content) for pattern in date_patterns):
                    results[i] = (content, score + 0.3)  # 增加权重
        
        # 增强关键词匹配：提取查询中的关键实体词（如公司名、商品名等）进行额外匹配
        enhanced_results = self._keyword_enhance(query, results)
        
        # 将关键词增强的结果直接加入，并使用更高的权重
        for content, score in enhanced_results:
            results.append((content, score * 2.0))  # 关键词匹配结果加倍权重
        
        # 去重并排序
        unique_results = {}
        for content, score in results:
            if content not in unique_results or score > unique_results[content]:
                unique_results[content] = score
        
        sorted_results = sorted(unique_results.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]
    
    def _keyword_enhance(self, query: str, current_results: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
        """
        通过关键词匹配增强检索结果
        
        Args:
            query: 查询文本
            current_results: 当前已有结果
            
        Returns:
            增强后的结果列表
        """
        enhanced = []
        
        # 提取查询中的关键实体（公司、股票、商品等）
        # 常见模式：股票代码、证券名称、商品名称等
        entity_patterns = [
            r'[\u4e00-\u9fff]{2,10}(?:证券|银行|公司|股份|基金|集团|科技)',  # 中文公司（不包含能源，因为会误匹配）
            r'\d{6}\.[A-Z]{2}',  # A股代码如 600109.SH
            r'[A-Z]{4,10}',  # 英文股票代码
            r'港股|A股|美股',
        ]
        
        # 提取查询中的实体词
        entities = []
        for pattern in entity_patterns:
            matches = re.findall(pattern, query)
            entities.extend(matches)
        
        # 语义扩展：只扩展精确的类别词，避免歧义词
        # 石油/能源类词汇必须单独出现，而不是作为"新能源"的一部分
        if '贵金属' in query:
            entities.extend(['黄金', '白银', '铂金', '钯金', '金价', '黄金走势'])
        if '石油' in query or '原油' in query:
            entities.extend(['石油', '原油', '布伦特', 'WTI'])
        if '能源' in query and '新能源' not in query:
            # 只有当查询包含"能源"但不包含"新能源"时才扩展
            entities.extend(['石油', '原油', '天然气', '煤炭'])
        
        # 如果有实体词，在所有记忆中搜索包含这些实体的记录
        if entities:
            all_memories = self._get_all_memory_contents()
            for content in all_memories:
                # 检查是否包含查询中的实体
                for entity in entities:
                    if entity in content:
                        # 使用非常高的分数确保关键词匹配优先
                        enhanced.append((content, 10.0))
                        break
        
        return enhanced
    
    def _get_all_memory_contents(self) -> List[str]:
        """
        获取所有情景记忆内容
        
        Returns:
            所有记忆内容列表
        """
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
        return memory_contents
    
    def _normalize_date_format(self, text: str) -> str:
        """
        标准化日期格式，将各种格式统一为 YYYY-MM-DD
        
        Args:
            text: 输入文本
            
        Returns:
            标准化后的文本
        """
        # 匹配 2026.4.6 或 2026.04.06 格式
        text = re.sub(r'(\d{4})[年\-\.](\d{1,2})[月\-\.](\d{1,2})日?', 
                     lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", text)
        return text
    
    def _search_bm25(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        """
        使用BM25搜索（支持中文分词和日期格式匹配）
        
        Args:
            query: 搜索查询
            top_k: 返回的结果数量
            
        Returns:
            相关记忆列表
        """
        # 读取所有情景记忆文件
        memory_contents = []
        memory_dates = []  # 保存每个记忆对应的日期
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
                                # 从文件名提取日期
                                date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
                                memory_dates.append(date_match.group(1) if date_match else "")
                except Exception as e:
                    print(f"读取 {filename} 失败: {e}")
        
        if not memory_contents:
            return []
        
        # 标准化查询中的日期格式
        normalized_query = self._normalize_date_in_text(query)
        
        # 预处理文本 - 使用jieba进行中文分词
        tokenized_corpus = []
        for content in memory_contents:
            tokens = []
            if has_bm25:
                try:
                    # 使用jieba精确模式分词
                    tokens = jieba.lcut(content.lower())
                    # 过滤短字符
                    tokens = [token for token in tokens if len(token) > 1]
                except Exception as e:
                    print(f"jieba分词失败: {e}")
                    # 回退到简单分词
                    tokens = [t for t in re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', content.lower()) if len(t) > 1]
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
                        # 使用jieba对查询进行分词
                        query_tokens = jieba.lcut(normalized_query.lower())
                        # 过滤短字符
                        query_tokens = [token for token in query_tokens if len(token) > 1]
                    except Exception as e:
                        print(f"jieba分词查询失败: {e}")
                        # 回退到简单分词
                        query_tokens = [t for t in re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', normalized_query.lower()) if len(t) > 1]
                scores = bm25.get_scores(query_tokens)
                
                # 排序并返回结果
                for i, score in enumerate(scores):
                    if score > 0:
                        results.append((memory_contents[i], score, memory_dates[i]))
            except Exception as e:
                print(f"BM25搜索失败: {e}")
        
        # 如果BM25失败，使用简单文本匹配
        if not results:
            for i, content in enumerate(memory_contents):
                similarity = 0.0
                if normalized_query.lower() in content.lower():
                    similarity = 0.8
                elif any(keyword in content.lower() for keyword in normalized_query.lower().split()):
                    similarity = 0.5
                
                if similarity > 0:
                    results.append((content, similarity, memory_dates[i]))
        
        # 日期匹配增强：检查查询中是否包含日期，并提升匹配度
        query_date_patterns = self._extract_date_patterns(query)
        if query_date_patterns:
            enhanced_results = []
            for content, score, date in results:
                # 如果记忆日期与查询中的日期匹配，提升分数
                for pattern in query_date_patterns:
                    if pattern in content or pattern in date:
                        score += 0.3  # 日期匹配加分
                        break
                enhanced_results.append((content, score))
            results = enhanced_results
        else:
            results = [(content, score) for content, score, _ in results]
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    
    def _normalize_date_in_text(self, text: str) -> str:
        """
        标准化文本中的日期格式，便于检索匹配
        
        Args:
            text: 输入文本
            
        Returns:
            标准化后的文本
        """
        # 处理 "2026.4.6" -> "2026-04-06"
        text = re.sub(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', 
                      lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", text)
        
        # 处理 "2026年4月6日" -> "2026-04-06"
        text = re.sub(r'(\d{4})年(\d{1,2})月(\d{1,2})日',
                      lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", text)
        
        return text
    
    def _extract_date_patterns(self, text: str) -> List[str]:
        """
        从文本中提取各种格式的日期模式
        
        Args:
            text: 输入文本
            
        Returns:
            日期模式列表
        """
        patterns = []
        
        # 提取 "2026.4.6" 格式
        dot_patterns = re.findall(r'\d{4}\.\d{1,2}\.\d{1,2}', text)
        for p in dot_patterns:
            # 转换为标准格式
            match = re.match(r'(\d{4})\.(\d{1,2})\.(\d{1,2})', p)
            if match:
                normalized = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
                patterns.append(normalized)
                patterns.append(p)  # 保留原格式
        
        # 提取 "2026-04-06" 格式
        dash_patterns = re.findall(r'\d{4}-\d{2}-\d{2}', text)
        patterns.extend(dash_patterns)
        
        # 提取 "2026年4月6日" 格式
        chinese_patterns = re.findall(r'\d{4}年\d{1,2}月\d{1,2}日', text)
        for p in chinese_patterns:
            match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', p)
            if match:
                normalized = f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
                patterns.append(normalized)
        
        return patterns
    
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
            query_embedding_model = _get_embedding_model()
            if query_embedding_model is None:
                return results
            
            query_embedding = query_embedding_model.encode(query)
            
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
    """长期记忆管理 - 结构化存储用户偏好和固定知识"""
    
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
            "user_preferences.md",
            "watchlist.md",
            "investment_profile.md"
        ]
        
        for category in categories:
            file_path = os.path.join(self.long_term_path, category)
            if not os.path.exists(file_path):
                self._init_file(category)
                print(f"创建分类文件: {category}")
    
    def _init_file(self, category: str):
        """
        初始化分类文件
        
        Args:
            category: 分类名称
        """
        file_path = os.path.join(self.long_term_path, category)
        
        if category == "user_preferences.md":
            content = """# user_preferences
最后更新: 

## 投资风格
- 类型: 
- 风险承受能力: 
- 投资期限: 

## 信息偏好
- 详细程度: 
- 关注重点: 
- 不喜欢: 

## 行业偏好
- 重点关注: 
- 避免行业: 
"""
        elif category == "watchlist.md":
            content = """# watchlist
最后更新: 

## 关注股票

## 关注公司

## 关注行业

"""
        elif category == "investment_profile.md":
            content = """# investment_profile
最后更新: 

## 投资目标
- 长期目标: 
- 短期目标: 

## 资产配置
- 股票占比: 
- 债券占比: 
- 现金占比: 
- 其他: 

## 投资策略
- 核心策略: 
- 止损策略: 
- 止盈策略: 

"""
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def _update_last_updated(self, category: str):
        """
        更新文件的最后更新时间
        
        Args:
            category: 分类名称
        """
        file_path = os.path.join(self.long_term_path, category)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            today = datetime.now().strftime("%Y-%m-%d")
            content = re.sub(r"最后更新:.*", f"最后更新: {today}", content)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            print(f"更新最后更新时间失败: {e}")
    
    def update_preference(self, section: str, key: str, value: str):
        """
        更新用户偏好
        
        Args:
            section: 部分名称（如 "投资风格"）
            key: 键名（如 "类型"）
            value: 值
        """
        file_path = os.path.join(self.long_term_path, "user_preferences.md")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            pattern = rf"- {key}:.*"
            replacement = f"- {key}: {value}"
            content = re.sub(pattern, replacement, content)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self._update_last_updated("user_preferences.md")
            print(f"更新偏好: {section} - {key} = {value}")
        except Exception as e:
            print(f"更新偏好失败: {e}")
    
    def add_to_watchlist(self, item_type: str, item: str, notes: str = ""):
        """
        添加到关注列表（每个分类最多保留20条）
        
        Args:
            item_type: 类型（"股票"、"公司"、"行业"）
            item: 项目名称
            notes: 备注
        """
        file_path = os.path.join(self.long_term_path, "watchlist.md")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            section_map = {
                "股票": "## 关注股票",
                "公司": "## 关注公司",
                "行业": "## 关注行业"
            }
            
            section = section_map.get(item_type)
            if section:
                entry = f"- {item}"
                if notes:
                    entry += f" ({notes})"
                
                if item not in content:
                    # 分割内容，找到对应section并处理
                    sections = re.split(r'(?=## )', content)
                    new_content = []
                    
                    for sec in sections:
                        if sec.strip().startswith(section):
                            # 处理当前section
                            lines = sec.split('\n')
                            header = lines[0]
                            items = [line for line in lines[1:] if line.strip().startswith('-')]
                            
                            # 添加新条目
                            items.append(entry)
                            
                            # 如果超过20条，移除最早的
                            if len(items) > 20:
                                items = items[-20:]
                            
                            # 重新构建section
                            new_sec = header + '\n' + '\n'.join(items) + '\n'
                            new_content.append(new_sec)
                        else:
                            new_content.append(sec)
                    
                    content = ''.join(new_content)
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    self._update_last_updated("watchlist.md")
                    print(f"添加到关注列表: {item_type} - {item}")
                else:
                    print(f"已在关注列表中: {item}")
        except Exception as e:
            print(f"添加到关注列表失败: {e}")
    
    def remove_from_watchlist(self, item_type: str, item: str):
        """
        从关注列表移除
        
        Args:
            item_type: 类型（"股票"、"公司"、"行业"）
            item: 项目名称
        """
        file_path = os.path.join(self.long_term_path, "watchlist.md")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            new_lines = []
            for line in lines:
                if item not in line:
                    new_lines.append(line)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            
            self._update_last_updated("watchlist.md")
            print(f"从关注列表移除: {item_type} - {item}")
        except Exception as e:
            print(f"从关注列表移除失败: {e}")
    
    def update_investment_profile(self, section: str, key: str, value: str):
        """
        更新投资档案
        
        Args:
            section: 部分名称
            key: 键名
            value: 值
        """
        file_path = os.path.join(self.long_term_path, "investment_profile.md")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            pattern = rf"- {key}:.*"
            replacement = f"- {key}: {value}"
            content = re.sub(pattern, replacement, content)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            self._update_last_updated("investment_profile.md")
            print(f"更新投资档案: {section} - {key} = {value}")
        except Exception as e:
            print(f"更新投资档案失败: {e}")
    
    def get_all(self) -> str:
        """
        获取所有长期记忆内容
        
        Returns:
            所有长期记忆的字符串
        """
        all_content = []
        for filename in os.listdir(self.long_term_path):
            if filename.endswith('.md'):
                file_path = os.path.join(self.long_term_path, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        all_content.append(f"\n---\n{content}")
                except Exception as e:
                    print(f"读取 {filename} 失败: {e}")
        
        return "\n".join(all_content)
    
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
                    # 简单的文本匹配
                    similarity = 0.0
                    if query.lower() in content.lower():
                        similarity = 0.9
                    elif any(keyword in content.lower() for keyword in query.lower().split()):
                        similarity = 0.6
                    
                    if similarity > 0:
                        filename = os.path.basename(file_path)
                        results.append((f"{filename}\n{content}", similarity))
            except Exception as e:
                print(f"搜索 {file_path} 失败: {e}")
        
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
    



class MemoryManager:
    """记忆管理器 - 协调工作记忆、情景记忆和长期记忆"""
    
    def __init__(self, working_memory_capacity: int = 20, save_interval: int = 20):
        """
        初始化记忆管理器
        
        Args:
            working_memory_capacity: 工作记忆容量（轮数）
            save_interval: 保存间隔，每多少轮对话保存一次情景记忆
        """
        # 工作记忆容量需要乘以2，因为一轮对话包含2条消息（user + assistant）
        self.working = WorkingMemory(working_memory_capacity * 2)
        self.episodic = EpisodicMemory()
        self.long_term = LongTermMemory()
        self.save_interval = save_interval
        self.conversation_count = 0  # 记录对话轮数（用户+agent为一轮）
        self.last_save_count = 0  # 上次保存时的对话轮数
        
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
        
        # 检查是否是assistant消息，如果是则增加对话轮数
        if role == "assistant":
            self.conversation_count += 1
            
            # 检查是否需要自动保存（基于对话轮数）
            if self.conversation_count - self.last_save_count >= self.save_interval:
                self.save_episodic_memory()
                self.last_save_count = self.conversation_count
                print(f"自动保存情景记忆，已完成 {self.conversation_count} 轮对话")
    

    
    def save_episodic_memory(self):
        """
        保存当前工作记忆到情景记忆，并更新长期记忆
        """
        summary = self.working.get_summary()
        if summary:
            metadata = {
                "type": "conversation_summary",
                "message_count": len(self.working.get_history()),
                "timestamp": datetime.now().isoformat(),
                "conversation_count": self.conversation_count
            }
            self.episodic.save_episodic_memory(summary, metadata)
            self.last_save_count = self.conversation_count
            
            # 立即更新长期记忆，使用当前的对话摘要
            self.refine_long_term_memory(conversation_summary=summary)
    
    def save_unsaved_memory(self):
        """
        保存未保存的工作记忆
        用于程序退出时调用
        """
        if self.conversation_count > self.last_save_count:
            unsaved_count = self.conversation_count - self.last_save_count
            print(f"保存未保存的工作记忆，共 {unsaved_count} 轮对话")
            
            # 只获取未保存的消息（每轮对话2条消息）
            unsaved_messages = unsaved_count * 2
            summary = self.working.get_recent_summary(unsaved_messages)
            
            if summary:
                metadata = {
                    "type": "conversation_summary",
                    "message_count": unsaved_messages,
                    "timestamp": datetime.now().isoformat(),
                    "conversation_count": self.conversation_count
                }
                self.episodic.save_episodic_memory(summary, metadata)
                self.last_save_count = self.conversation_count
                
                # 立即更新长期记忆，使用当前的对话摘要
                self.refine_long_term_memory(conversation_summary=summary)
            return True
        return False
    
    def refine_long_term_memory(self, conversation_summary: str = None, query: str = None):
        """
        从对话历史中提炼长期记忆 - 调用LLM分析并更新
        
        Args:
            conversation_summary: 对话摘要（如果提供，直接使用这个）
            query: 提炼的主题
        """
        print("正在分析对话历史，提炼长期记忆...")
        
        # 构建提示词
        if conversation_summary:
            memories_text = conversation_summary
        else:
            # 如果没有提供，从情景记忆获取
            recent_memories = self.episodic.load_recent_memories(days=1)
            if not recent_memories:
                print("没有最近的情景记忆可分析")
                return
            memories_text = "\n\n".join(recent_memories[-3:])
        
        prompt = f"""你是一个金融投资助手的记忆整理专家。请分析以下对话历史，提取结构化的长期记忆信息。

对话历史：
{memories_text}

请提取以下信息，以JSON格式返回，不要包含其他文本：
{{
  "user_preferences": {{  // 用户偏好
    "investment_style": {{  // 投资风格
      "type": "价值投资/成长投资/趋势投资等",
      "risk_tolerance": "低/中/高",
      "investment_horizon": "短期/中期/长期"
    }},
    "info_preferences": {{  // 信息偏好
      "detail_level": "简洁/详细",
      "focus_areas": "关注的重点领域",
      "dislikes": "不喜欢的内容"
    }},
    "industry_preferences": {{  // 行业偏好
      "focus_industries": "重点关注行业",
      "avoid_industries": "避免行业"
    }}
  }},
  "watchlist": {{  // 关注列表
    "stocks": ["股票1", "股票2"],
    "companies": ["公司1", "公司2"],
    "industries": ["行业1", "行业2"]
  }},
  "investment_profile": {{  // 投资档案
    "goals": {{  // 投资目标
      "long_term": "长期目标",
      "short_term": "短期目标"
    }},
    "allocation": {{  // 资产配置
      "stock_ratio": "股票占比",
      "bond_ratio": "债券占比",
      "cash_ratio": "现金占比",
      "other": "其他"
    }},
    "strategy": {{  // 投资策略
      "core_strategy": "核心策略",
      "stop_loss": "止损策略",
      "take_profit": "止盈策略"
    }}
  }}
}}

如果某个字段没有信息，请保持为空字符串或空数组。只返回JSON，不要有其他说明。"""
        
        try:
            # 调用LLM分析
            llm_response = generate_text(prompt)
            
            # 尝试解析JSON
            import json
            # 清理响应，提取JSON部分
            json_match = re.search(r'\{[\s\S]*\}', llm_response)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                
                # 更新用户偏好
                if "user_preferences" in data:
                    prefs = data["user_preferences"]
                    if "investment_style" in prefs:
                        style = prefs["investment_style"]
                        if style.get("type"):
                            self.long_term.update_preference("投资风格", "类型", style["type"])
                        if style.get("risk_tolerance"):
                            self.long_term.update_preference("投资风格", "风险承受能力", style["risk_tolerance"])
                        if style.get("investment_horizon"):
                            self.long_term.update_preference("投资风格", "投资期限", style["investment_horizon"])
                    if "info_preferences" in prefs:
                        info = prefs["info_preferences"]
                        if info.get("detail_level"):
                            self.long_term.update_preference("信息偏好", "详细程度", info["detail_level"])
                        if info.get("focus_areas"):
                            self.long_term.update_preference("信息偏好", "关注重点", info["focus_areas"])
                        if info.get("dislikes"):
                            self.long_term.update_preference("信息偏好", "不喜欢", info["dislikes"])
                    if "industry_preferences" in prefs:
                        industry = prefs["industry_preferences"]
                        if industry.get("focus_industries"):
                            self.long_term.update_preference("行业偏好", "重点关注", industry["focus_industries"])
                        if industry.get("avoid_industries"):
                            self.long_term.update_preference("行业偏好", "避免行业", industry["avoid_industries"])
                
                # 更新关注列表
                if "watchlist" in data:
                    watchlist = data["watchlist"]
                    for stock in watchlist.get("stocks", []):
                        if stock:
                            self.long_term.add_to_watchlist("股票", stock)
                    for company in watchlist.get("companies", []):
                        if company:
                            self.long_term.add_to_watchlist("公司", company)
                    for industry in watchlist.get("industries", []):
                        if industry:
                            self.long_term.add_to_watchlist("行业", industry)
                
                # 更新投资档案
                if "investment_profile" in data:
                    profile = data["investment_profile"]
                    if "goals" in profile:
                        goals = profile["goals"]
                        if goals.get("long_term"):
                            self.long_term.update_investment_profile("投资目标", "长期目标", goals["long_term"])
                        if goals.get("short_term"):
                            self.long_term.update_investment_profile("投资目标", "短期目标", goals["short_term"])
                    if "allocation" in profile:
                        alloc = profile["allocation"]
                        if alloc.get("stock_ratio"):
                            self.long_term.update_investment_profile("资产配置", "股票占比", alloc["stock_ratio"])
                        if alloc.get("bond_ratio"):
                            self.long_term.update_investment_profile("资产配置", "债券占比", alloc["bond_ratio"])
                        if alloc.get("cash_ratio"):
                            self.long_term.update_investment_profile("资产配置", "现金占比", alloc["cash_ratio"])
                        if alloc.get("other"):
                            self.long_term.update_investment_profile("资产配置", "其他", alloc["other"])
                    if "strategy" in profile:
                        strat = profile["strategy"]
                        if strat.get("core_strategy"):
                            self.long_term.update_investment_profile("投资策略", "核心策略", strat["core_strategy"])
                        if strat.get("stop_loss"):
                            self.long_term.update_investment_profile("投资策略", "止损策略", strat["stop_loss"])
                        if strat.get("take_profit"):
                            self.long_term.update_investment_profile("投资策略", "止盈策略", strat["take_profit"])
                
                print("长期记忆更新完成！")
            else:
                print("无法解析LLM响应")
                print(f"LLM响应: {llm_response[:200]}...")
                
        except Exception as e:
            print(f"提炼长期记忆失败: {e}")
            import traceback
            traceback.print_exc()
    
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


def save_unsaved_memory():
    """
    保存未保存的工作记忆
    用于程序退出时调用
    """
    return memory_manager.save_unsaved_memory()


def update_long_term_preference(section: str, key: str, value: str):
    """
    更新用户偏好
    
    Args:
        section: 部分名称
        key: 键名
        value: 值
    """
    global memory_manager
    if memory_manager:
        memory_manager.long_term.update_preference(section, key, value)


def add_to_watchlist(item_type: str, item: str, notes: str = ""):
    """
    添加到关注列表
    
    Args:
        item_type: 类型（"股票"、"公司"、"行业"）
        item: 项目名称
        notes: 备注
    """
    global memory_manager
    if memory_manager:
        memory_manager.long_term.add_to_watchlist(item_type, item, notes)


def remove_from_watchlist(item_type: str, item: str):
    """
    从关注列表移除
    
    Args:
        item_type: 类型
        item: 项目名称
    """
    global memory_manager
    if memory_manager:
        memory_manager.long_term.remove_from_watchlist(item_type, item)


def update_investment_profile(section: str, key: str, value: str):
    """
    更新投资档案
    
    Args:
        section: 部分名称
        key: 键名
        value: 值
    """
    global memory_manager
    if memory_manager:
        memory_manager.long_term.update_investment_profile(section, key, value)


def get_all_long_term_memory() -> str:
    """
    获取所有长期记忆内容
    
    Returns:
        所有长期记忆字符串
    """
    global memory_manager
    if memory_manager:
        return memory_manager.long_term.get_all()
    return ""
