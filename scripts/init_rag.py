# scripts/init_rag.py

import sys
import os

# 将项目根目录添加到 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.rag import load_and_preprocess_reports, reset_chroma_collection, add_documents_to_chroma

def main():
    print("开始初始化 RAG 数据库...")
    
    # 1. 加载和预处理研报
    print("正在加载和预处理研报...")
    documents = load_and_preprocess_reports()
    
    if not documents:
        print("警告: 未找到任何研报文档。请检查 data/reports/ 目录。")
        return
    else:
        print(f"成功预处理 {len(documents)} 个文档块。")

    # 2. 重置 ChromaDB 集合
    print("正在重置 ChromaDB 集合...")
    collection = reset_chroma_collection()
    
    # 3. 添加文档到 ChromaDB
    print("正在将文档添加到 ChromaDB...")
    add_documents_to_chroma(documents, collection)
    
    print("RAG 数据库初始化完成！")

if __name__ == "__main__":
    main()
