"""
统一 RAG 检索系统 — 代码 + 文档，不同切块策略，同一个知识库
- 代码：按函数/类边界切（CodeChunker）
- 文档：按标题/段落切（DocumentChunker）
- 检索：支持按 doc_type 过滤（code / document / all）
"""
import sys, os
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import chromadb
from sentence_transformers import SentenceTransformer
from openai import OpenAI

import chunkers


# ─── 索引构建 ────────────────────────────────────

def build_unified_index(directory: str):
    """扫描目录，用不同策略切代码和文档，统一存入 ChromaDB"""
    print(f"扫描并切分: {directory}\n")
    all_chunks, stats = chunkers.chunk_directory(directory)

    print(f"\n=== 切块统计 ===")
    print(f"代码: {stats['code_files']} 文件 → {stats['code_chunks']} 块")
    print(f"文档: {stats['doc_files']} 文件 → {stats['doc_chunks']} 块")
    print(f"总计: {len(all_chunks)} 块")

    if not all_chunks:
        print("没有找到任何可索引的内容！")
        return None, None

    # 加载 Embedding 模型
    print("\n加载 embedding 模型...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    # 向量化
    print("向量化中...")
    texts = [c["content"] for c in all_chunks]
    embeddings = model.encode(texts, show_progress_bar=True)

    # 存入 ChromaDB（新 collection，不影响旧的）
    chroma_path = os.path.join(directory, ".chroma_db")
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection("unified_knowledge")

    # 清空旧数据
    try:
        existing = collection.get()
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
    except Exception:
        pass

    # 批量写入
    batch_size = 100
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i + batch_size]
        collection.add(
            ids=[c["id"] for c in batch],
            documents=[c["content"] for c in batch],
            embeddings=embeddings[i:i + batch_size].tolist(),
            metadatas=[{
                "doc_type": c["doc_type"],
                "source": c["source"],
                "elem_or_section": c.get("element") or c.get("section") or "",
            } for c in batch],
        )

    print(f"索引构建完成！{len(all_chunks)} 个块已存入 {chroma_path}")
    return collection, model


# ─── 检索 ────────────────────────────────────

def search(collection, model, query: str, top_k: int = 3,
           filter_type: str = "all"):
    """
    检索知识库。
    filter_type: "all" / "code" / "document"
    """
    query_embedding = model.encode([query])[0]

    # ChromaDB where 过滤
    where_filter = None
    if filter_type == "code":
        where_filter = {"doc_type": "code"}
    elif filter_type == "document":
        where_filter = {"doc_type": "document"}

    results = collection.query(
        query_embeddings=[query_embedding.tolist()],
        n_results=top_k,
        where=where_filter,
    )

    if not results["documents"] or not results["documents"][0]:
        return [], []

    chunks = results["documents"][0]
    metas = results["metadatas"][0] if results["metadatas"] else []
    return chunks, metas


# ─── 问答 ────────────────────────────────────

def ask(collection, model, question: str, filter_type: str = "all") -> str:
    """检索 + LLM 回答"""
    client = OpenAI(
        api_key="sk-248381b7b8a64de3879fccdfd2f0e213",
        base_url="https://api.deepseek.com",
    )

    chunks, metas = search(collection, model, question, filter_type=filter_type)

    if not chunks:
        return "(知识库中没有找到相关内容)"

    # 拼 Prompt，标注来源类型
    context_parts = []
    for i, (chunk, meta) in enumerate(zip(chunks, metas)):
        type_label = "📄文档" if meta.get("doc_type") == "document" else "💻代码"
        src = meta.get("source", "unknown")
        elem = meta.get("elem_or_section", "")
        label = f"[{type_label}] 来源: {src}"
        if elem:
            label += f" | {elem}"
        context_parts.append(f"{label}\n{chunk}")

    context = "\n\n---\n\n".join(context_parts)

    prompt = f"""你是一个问答助手。请根据以下资料回答问题。
资料中有些来自代码文件，有些来自文档。如果资料中没有答案，请如实说"资料中未找到相关信息"。

资料：
{context}

问题：{question}

回答："""

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )

    answer = response.choices[0].message.content

    # 显示来源摘要
    src_set = set()
    for m in metas:
        t = "代码" if m.get("doc_type") == "code" else "文档"
        src_set.add(f"[{t}] {m['source']}")

    src_summary = ", ".join(sorted(src_set))
    return f"{answer}\n\n(来源: {src_summary})"


# ─── 交互入口 ────────────────────────────────────

def print_result(chunks, metas):
    """详细打印检索结果"""
    if not chunks:
        print("  (无结果)")
        return
    for i, (chunk, meta) in enumerate(zip(chunks, metas)):
        t = meta.get("doc_type", "?")
        icon = "💻" if t == "code" else "📄"
        src = meta.get("source", "?")
        elem = meta.get("elem_or_section", "")
        preview = chunk[:200].replace("\n", "\\n")
        print(f"  [{i+1}] {icon} {src} | {elem}")
        print(f"      {preview}...")
        print()


if __name__ == "__main__":
    target_dir = r"D:\agent_learning"

    # 建索引
    collection, model = build_unified_index(target_dir)
    if collection is None:
        sys.exit(1)

    print("\n" + "=" * 55)
    print("  统一 RAG 知识库就绪！")
    print("  代码块（按函数/类切）+ 文档块（按标题/段落切）")
    print("  命令: all / code / doc 切换检索范围, exit 退出")
    print("=" * 55)

    filter_type = "all"

    while True:
        try:
            raw = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not raw:
            continue

        if raw.lower() in ("exit", "quit", "q"):
            break

        # 切换命令
        if raw.lower() == "all":
            filter_type = "all"
            print("[检索范围 → 全部（代码+文档）]")
            continue
        if raw.lower() == "code":
            filter_type = "code"
            print("[检索范围 → 仅代码]")
            continue
        if raw.lower() == "doc":
            filter_type = "document"
            print("[检索范围 → 仅文档]")
            continue

        # 先展示检索结果
        chunks, metas = search(collection, model, raw, top_k=3, filter_type=filter_type)
        print(f"\n检索结果（范围={filter_type}）：")
        print_result(chunks, metas)

        # 再生成回答
        print("生成回答中...")
        answer = ask(collection, model, raw, filter_type=filter_type)
        print(f"\n[回答] {answer}")
