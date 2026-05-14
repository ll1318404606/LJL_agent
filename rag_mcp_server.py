"""
RAG MCP Server — 知识库工具
Agent 通过 MCP 协议调用搜索知识库
"""
import os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp.server.fastmcp import FastMCP
from sentence_transformers import SentenceTransformer
import chromadb

mcp = FastMCP("rag-server")

# 全局状态
_model = None
_collection = None
INDEX_DIR = r"D:\agent_learning"
CHROMA_PATH = os.path.join(INDEX_DIR, ".chroma_db")


def get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection = client.get_or_create_collection("agent_knowledge")
    return _collection


@mcp.tool()
async def search_knowledge(query: str) -> str:
    """搜索知识库（包含项目所有代码和文档），返回最相关的资料片段"""
    collection = get_collection()
    model = get_model()
    embedding = model.encode([query])[0]

    results = collection.query(query_embeddings=[embedding.tolist()], n_results=3)
    if not results["documents"] or not results["documents"][0]:
        return "(知识库中没有找到相关内容)"

    output = []
    for i, chunk in enumerate(results["documents"][0]):
        src = results["metadatas"][0][i]["source"] if results["metadatas"] else "unknown"
        output.append(f"[来源: {src}]\n{chunk}")

    return "\n\n---\n\n".join(output)


@mcp.tool()
async def reindex_knowledge() -> str:
    """重建知识库索引（添加新文件后需要调用）"""
    import asyncio
    # 用 subprocess 跑 rag_demo.py 的建索引部分
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", f"""
import sys; sys.path.insert(0, r'{INDEX_DIR}')
from rag_demo import build_index
build_index(r'{INDEX_DIR}')
""",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode == 0:
        return "知识库索引已重建"
    return f"重建失败: {stderr.decode()}"


if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_stdio_async())
