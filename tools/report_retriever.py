# tools/report_retriever.py

from typing import List, Dict, Any
from utils.rag import get_chroma_collection, query_chroma, load_and_preprocess_reports, add_documents_to_chroma
import os

def retrieve_reports(query: str, n_results: int = 5, filters: Dict = None) -> List[Dict[str, Any]]:
    """
    根据用户查询检索最相关的研报内容。
    如果 ChromaDB 中没有文档，则先加载并添加研报。
    
    Args:
        query: 查询文本
        n_results: 返回结果数量
        filters: 元数据过滤条件 (例如 {"ticker": "NVDA"})
    """
    collection = get_chroma_collection()
    
    # 检查集合是否为空，如果为空则加载并添加文档
    if collection.count() == 0:
        print("ChromaDB 集合为空，开始加载和预处理研报...")
        reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "reports")
        documents = load_and_preprocess_reports(reports_dir)
        add_documents_to_chroma(documents, collection)
        print(f"已向 ChromaDB 添加 {len(documents)} 个文档块。")

    retrieved_docs = query_chroma(query, collection, n_results, where=filters)
    return retrieved_docs

if __name__ == "__main__":
    # 示例用法
    # 确保 data/reports 目录存在并包含一些研报文件
    sample_report_path = "../data/reports/sample_report.txt"
    os.makedirs(os.path.dirname(sample_report_path), exist_ok=True)
    with open(sample_report_path, "w", encoding="utf-8") as f:
        f.write("这是一个示例研报内容。它包含了一些关于金融市场的信息。")
        f.write("第二段内容，用于测试分块功能。")
    
    query = "金融市场最近有什么重要信息？"
    print(f"查询: {query}")
    results = retrieve_reports(query)
    
    print("检索结果:")
    for doc in results:
        print(f"  内容: {doc['content'][:50]}...")
        print(f"  来源: {doc['metadata']['source']}")
    
    os.remove(sample_report_path)
    print(f"已清理示例文件: {sample_report_path}")
