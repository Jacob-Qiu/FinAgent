
import os
import sys
import shutil
import chromadb
from chromadb.config import Settings
import time

# 添加项目根目录到 sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.rag import extract_text_from_pdf, chunk_text, get_chroma_collection

CHROMA_DB_PATH = "./chroma_db"
DATA_DIR = "data/reports"

def reset_database():
    """彻底清除旧格式数据"""
    if os.path.exists(CHROMA_DB_PATH):
        print(f"正在删除旧数据库: {CHROMA_DB_PATH}")
        shutil.rmtree(CHROMA_DB_PATH)
    else:
        print("旧数据库不存在，跳过删除。")
    
    # 等待文件系统释放锁
    time.sleep(1)

def ingest_data():
    """递归读取 data/reports/ 下的子文件夹并入库"""
    print("开始初始化 ChromaDB...")
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_or_create_collection(name="finagent_reports")
    
    # 嵌入模型 (需要与 rag.py 保持一致，这里假设 rag.py 使用的是默认或通过 SentenceTransformer 生成的 embedding)
    # 注意：如果 utils.rag.py 中 add_documents_to_chroma 负责生成 embedding，我们应该复用它
    # 但根据 utils/rag.py 的代码，它是在 load_and_preprocess_reports 中生成 embedding 的。
    # 为了保持一致性，我们这里直接调用 sentence_transformers 生成 embedding
    
    from sentence_transformers import SentenceTransformer
    print("加载 Embedding 模型...")
    model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')

    if not os.path.exists(DATA_DIR):
        print(f"数据目录不存在: {DATA_DIR}")
        return

    print(f"开始扫描目录: {DATA_DIR}")
    
    documents = []
    metadatas = []
    ids = []
    embeddings = []
    
    total_files = 0
    
    for root, dirs, files in os.walk(DATA_DIR):
        # 获取 category (文件夹名)
        rel_path = os.path.relpath(root, DATA_DIR)
        if rel_path == ".":
            continue
            
        category = os.path.basename(root)
        print(f"正在处理分类: {category}")
        
        for file_name in files:
            if file_name.startswith('.'):
                continue
                
            if not (file_name.endswith('.pdf') or file_name.endswith('.txt') or file_name.endswith('.md')):
                continue
            
            file_path = os.path.join(root, file_name)
            
            # 解析 ticker (文件名首段)
            # 格式通常为: Ticker_Date_...
            parts = file_name.split('_')
            ticker = parts[0]
            
            # 提取文本
            content = ""
            try:
                if file_name.endswith(".pdf"):
                    content = extract_text_from_pdf(file_path)
                else:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
            except Exception as e:
                print(f"读取文件失败 {file_name}: {e}")
                continue
                
            if not content:
                print(f"文件内容为空: {file_name}")
                continue
                
            total_files += 1
            
            # 分块
            chunks = chunk_text(content)
            
            for i, chunk in enumerate(chunks):
                doc_id = f"{file_name}_{i}"
                
                # 生成 embedding
                embedding = model.encode(chunk).tolist()
                
                # 构造 metadata
                metadata = {
                    "source": file_name,
                    "category": category,
                    "ticker": ticker,
                    "chunk_id": i
                }
                
                documents.append(chunk)
                metadatas.append(metadata)
                ids.append(doc_id)
                embeddings.append(embedding)
                
    # 批量入库
    if documents:
        print(f"正在入库 {len(documents)} 个文本块 (来自 {total_files} 个文件)...")
        # ChromaDB 建议分批插入以避免内存问题，这里简单起见一次性插入，如果数据量大需分批
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            end = min(i + batch_size, len(documents))
            collection.add(
                documents=documents[i:end],
                metadatas=metadatas[i:end],
                ids=ids[i:end],
                embeddings=embeddings[i:end]
            )
        print("入库完成！")
    else:
        print("未找到有效文档。")

def verify_data():
    """验证入库结果"""
    print("\n=== 验证入库结果 ===")
    client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
    collection = client.get_collection(name="finagent_reports")
    
    count = collection.count()
    print(f"总记录数: {count}")
    
    if count > 0:
        results = collection.get(limit=5)
        print("前 5 条记录的元数据:")
        for i, metadata in enumerate(results['metadatas']):
            print(f"Record {i+1}: {metadata}")
            # 检查关键字段
            if 'category' not in metadata or 'ticker' not in metadata:
                print(f"❌ 警告: 元数据缺失关键字段! {metadata}")
            else:
                print(f"✅ category={metadata['category']}, ticker={metadata['ticker']}")

if __name__ == "__main__":
    reset_database()
    ingest_data()
    verify_data()
