# utils/rag.py

import os
import json
from typing import List, Dict, Any
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import tiktoken
import chromadb
from chromadb.utils import embedding_functions

# 初始化 SentenceTransformer 模型
# 可以根据需求选择不同的模型，例如 'all-MiniLM-L6-v2' 或 'BAAI/bge-small-en-v1.5'
# 这里我们使用一个通用的多语言模型，如果研报主要是中文，可以考虑使用中文模型
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

# 初始化 tiktoken 编码器
# 可以根据实际使用的LLM选择合适的编码器，例如 'cl100k_base' 对应 OpenAI 的 GPT 系列
encoding = tiktoken.get_encoding("cl100k_base")

# ChromaDB 客户端和集合
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "finagent_reports"

def get_chroma_collection():
    """
    初始化 ChromaDB 客户端并获取一个集合。
    """
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    # 使用 SentenceTransformer 模型的嵌入函数
    # 注意：这里我们直接使用 model.encode，所以 embedding_function 可以设置为 None
    # 或者创建一个包装器，确保 ChromaDB 使用相同的模型
    # 为了简化，我们直接在添加文档时提供嵌入向量
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        # embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(model_name='paraphrase-multilingual-MiniLM-L12-v2')
        # 由于我们手动生成嵌入，这里不需要指定 embedding_function
    )
    return collection

def reset_chroma_collection():
    """
    清空并重新创建 ChromaDB 集合。
    用于在重新导入数据时确保数据的唯一性和清洁性。
    """
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"已删除旧集合: {COLLECTION_NAME}")
    except ValueError:
        print(f"集合 {COLLECTION_NAME} 不存在，无需删除")
    
    return client.get_or_create_collection(name=COLLECTION_NAME)

def load_and_preprocess_reports(reports_dir: str = "data/reports/") -> List[Dict[str, Any]]:
    """
    加载指定目录下的研报，进行预处理（文本提取、分块、元数据提取），并生成嵌入向量。
    支持 PDF 和 TXT/MD 文件。
    
    功能升级：
    1. 识别类别：读取文件所在的子文件夹名作为 category。
    2. 解析文件名：从标准化的文件名 (Ticker_Date_Broker_Subject) 中提取元数据。
    3. 处理个股关联：标记是否为个股研报。
    """
    processed_documents = []
    
    # 确保路径存在
    if not os.path.exists(reports_dir):
        print(f"目录不存在: {reports_dir}")
        return []

    print(f"开始扫描目录: {reports_dir}")
    for root, dirs, files in os.walk(reports_dir):
        # 识别类别：读取文件所在的子文件夹名
        # 如果 root 是 reports_dir 本身，category 为 "Uncategorized"
        rel_path = os.path.relpath(root, reports_dir)
        category = rel_path if rel_path != "." else "Uncategorized"
        
        for file_name in files:
            # 跳过隐藏文件
            if file_name.startswith('.'):
                continue
                
            file_path = os.path.join(root, file_name)
            content = ""
            
            # 提取文本
            if file_name.endswith(".pdf"):
                content = extract_text_from_pdf(file_path)
            elif file_name.endswith(".txt") or file_name.endswith(".md"):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception as e:
                    print(f"读取文件失败 {file_path}: {e}")
                    continue
            else:
                continue # 跳过不支持的文件类型
            
            if not content:
                print(f"文件内容为空或无法读取: {file_name}")
                continue

            # 解析文件名元数据
            # 智能解析：尝试寻找日期（8位数字）来定位其他字段
            # 兼容格式：Ticker_Date_Broker_Subject 或 Code_Name_Date_Broker_Subject
            name_without_ext = os.path.splitext(file_name)[0]
            parts = name_without_ext.split('_')
            
            metadata = {
                "source": file_name,
                "category": category
            }
            
            # 寻找日期（8位数字）
            date_index = -1
            for i, part in enumerate(parts):
                if part.isdigit() and len(part) == 8:
                    date_index = i
                    break
            
            if date_index != -1:
                metadata["publish_date"] = parts[date_index]
                # Ticker 始终取第一部分
                metadata["ticker"] = parts[0]
                
                # Broker 通常在日期之后
                if date_index + 1 < len(parts):
                    metadata["broker"] = parts[date_index + 1]
                else:
                    metadata["broker"] = "UNKNOWN"
                    
                # Subject 是 Broker 之后的所有内容
                if date_index + 2 < len(parts):
                    metadata["subject"] = "_".join(parts[date_index + 2:])
                else:
                    metadata["subject"] = ""
            elif len(parts) >= 3:
                # 找不到日期时的回退逻辑：按位置解析
                metadata["ticker"] = parts[0]
                metadata["publish_date"] = parts[1]
                metadata["broker"] = parts[2]
                metadata["subject"] = "_".join(parts[3:]) if len(parts) > 3 else ""
            else:
                # 无法解析标准格式时的回退
                metadata["ticker"] = "UNKNOWN"
                metadata["publish_date"] = "UNKNOWN"
                metadata["broker"] = "UNKNOWN"
                metadata["subject"] = name_without_ext

            # 处理个股关联
            # 如果 ticker 不是 INDUSTRY 或 MACRO，确保它能作为核心索引
            if metadata["ticker"] not in ["INDUSTRY", "MACRO"]:
                metadata["is_stock_specific"] = True
            else:
                metadata["is_stock_specific"] = False

            # 分块并生成嵌入
            chunks = chunk_text(content)
            for i, chunk in enumerate(chunks):
                embedding = model.encode(chunk).tolist()
                
                # 为每个 chunk 创建包含完整元数据的文档对象
                doc_metadata = metadata.copy()
                doc_metadata["chunk_id"] = i
                
                processed_documents.append({
                    "id": f"{file_name}_{i}",
                    "content": chunk,
                    "embedding": embedding,
                    "metadata": doc_metadata
                })
                
    return processed_documents

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    从 PDF 文件中提取文本。
    """
    text = ""
    try:
        reader = PdfReader(pdf_path)
        for page in reader.pages:
            text += page.extract_text() or ""
    except Exception as e:
        print(f"Error reading PDF {pdf_path}: {e}")
    return text

def chunk_text(text: str, max_tokens: int = 500, overlap: int = 50) -> List[str]:
    """
    将文本分块，以 token 数量为基准，并支持重叠。
    """
    tokens = encoding.encode(text)
    chunks = []
    for i in range(0, len(tokens), max_tokens - overlap):
        chunk_tokens = tokens[i : i + max_tokens]
        chunks.append(encoding.decode(chunk_tokens))
    return chunks

def add_documents_to_chroma(documents: List[Dict[str, Any]], collection):
    """
    将处理后的文档块添加到 ChromaDB 集合中。
    """
    if not documents:
        print("没有文档需要添加")
        return
    
    # 批量添加，避免一次性过大
    batch_size = 100
    total_docs = len(documents)
    
    print(f"准备添加 {total_docs} 个文档块到 ChromaDB...")
    
    for i in range(0, total_docs, batch_size):
        batch = documents[i : i + batch_size]
        
        ids = [doc["id"] for doc in batch]
        embeddings = [doc["embedding"] for doc in batch]
        metadatas = [doc["metadata"] for doc in batch] # 使用完整的 metadata
        documents_content = [doc["content"] for doc in batch]
        
        try:
            collection.add(
                embeddings=embeddings,
                metadatas=metadatas,
                documents=documents_content,
                ids=ids
            )
        except Exception as e:
            print(f"添加批次 {i//batch_size} 失败: {e}")
            
    print(f"成功向 ChromaDB 添加 {total_docs} 个文档块。")

def query_chroma(query_text: str, collection, n_results: int = 5, where: Dict = None) -> List[Dict[str, Any]]:
    """
    根据查询文本在 ChromaDB 中进行相似性搜索，返回最相关的文档块。
    支持通过 where 参数进行元数据过滤。
    """
    query_embedding = model.encode([query_text]).tolist()
    
    results = collection.query(
        query_embeddings=query_embedding,
        n_results=n_results,
        where=where,
        include=['documents', 'metadatas']
    )
    
    retrieved_docs = []
    if results and results['documents']:
        for i in range(len(results['documents'][0])):
            retrieved_docs.append({
                "content": results['documents'][0][i],
                "metadata": results['metadatas'][0][i]
            })
    return retrieved_docs

# 示例用法 (可以在其他地方调用)
if __name__ == "__main__":
    # 确保 data/reports 目录存在并包含一些研报文件
    # 例如，可以手动创建 data/reports/sample.txt 或 data/reports/sample.pdf
    # 并放入一些文本内容
    
    # 创建一个示例报告文件用于测试
    sample_report_path = "data/reports/sample_report.txt"
    # 确保目录存在
    os.makedirs(os.path.dirname(sample_report_path), exist_ok=True)
    
    with open(sample_report_path, "w", encoding="utf-8") as f:
        f.write("这是一个示例研报内容。它包含了一些关于金融市场的信息。")
        f.write("第二段内容，用于测试分块功能。")
    
    print("开始加载和预处理研报...")
    documents = load_and_preprocess_reports()
    print(f"处理完成，共生成 {len(documents)} 个文档块。")
    
    # 初始化 ChromaDB 集合 (使用 reset 模式)
    collection = reset_chroma_collection()
    
    # 将文档添加到 ChromaDB
    add_documents_to_chroma(documents, collection)
    
    # 执行查询
    query = "金融市场最近有什么重要信息？"
    print(f"\n查询: {query}")
    retrieved_results = query_chroma(query, collection)
    
    print("检索结果:")
    for doc in retrieved_results:
        print(f"  内容: {doc['content'][:50]}...")
        print(f"  来源: {doc['metadata']['source']}")
    
    # 清理示例文件和 ChromaDB
    if os.path.exists(sample_report_path):
        os.remove(sample_report_path)
        print(f"已清理示例文件: {sample_report_path}")
    
