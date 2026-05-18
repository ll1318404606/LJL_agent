"""
RAG Demo — 给 Agent 加上"知识库"能力
核心流程：建索引（一次性）→ 查询时检索 → 拼进 Prompt → LLM 回答
"""
import sys, os
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ─── 第一步：建索引 ────────────────────────────────────

def build_index(directory: str):
    """扫描目录中所有 .py 和 .md 文件，切块、向量化、存入 ChromaDB"""
    import chromadb
    from sentence_transformers import SentenceTransformer

    print("加载 embedding 模型...")
    model = SentenceTransformer("all-MiniLM-L6-v2")  # 本地小模型，免费

    # 收集文档
    documents = []
    for root, _, files in os.walk(directory):
        for fname in files:
            if fname.endswith((".py", ".md")):
                path = os.path.join(root, fname)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except Exception:
                    continue
                if not content.strip():
                    continue

                # ── 切块（Chunking）──
                # 按行切，每块约 30 行，重叠 5 行（代码文件不乱切行）
                lines = content.split("\n")
                chunk_lines = 30
                overlap_lines = 5
                chunks = []
                line_start = 0
                while line_start < len(lines):
                    line_end = min(line_start + chunk_lines, len(lines))
                    chunks.append("\n".join(lines[line_start:line_end]))
                    line_start += chunk_lines - overlap_lines

                for i, chunk in enumerate(chunks):
                    if chunk.strip():
                        documents.append({
                            "id": f"{fname}_{i}",
                            "content": chunk,
                            "source": fname,
                            "path": path,
                        })

    print(f"切分完成，共 {len(documents)} 个块")

    # 向量化
    print("向量化中...")
    texts = [d["content"] for d in documents]
    embeddings = model.encode(texts, show_progress_bar=True)

    # 存入 ChromaDB
    chroma_path = os.path.join(directory, ".chroma_db")
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection("agent_knowledge")

    # 清空旧数据
    try:
        collection.delete(ids=collection.get()["ids"])
    except Exception:
        pass

    # 批量写入
    batch_size = 100
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        collection.add(
            ids=[d["id"] for d in batch],
            documents=[d["content"] for d in batch],
            embeddings=embeddings[i:i + batch_size].tolist(),
            metadatas=[{"source": d["source"], "path": d["path"]} for d in batch],
        )

    print(f"索引进完毕，{len(documents)} 个块已存入 {chroma_path}")
    return collection, model


# ─── 第二步：检索 ────────────────────────────────────

def search(collection, model, query: str, top_k: int = 3) -> list[str]:
    """用问题去向量库中搜最相关的块"""
    from sentence_transformers import SentenceTransformer
    query_embedding = model.encode([query])[0]
    results = collection.query(query_embeddings=[query_embedding.tolist()], n_results=top_k)
    chunks = results["documents"][0] if results["documents"] else []
    sources = results["metadatas"][0] if results["metadatas"] else []
    return chunks, sources


# ─── 第三步：回答 ────────────────────────────────────

def ask(collection, model, question: str) -> str:
    """检索 + LLM 回答"""
    from openai import OpenAI

    chunks, sources = search(collection, model, question)

    if not chunks:
        return "(知识库中没有找到相关内容)"

    # 拼 Prompt
    context = "\n\n---\n\n".join(chunks)
    prompt = f"""你是一个问答助手。请根据以下资料回答问题。
如果资料中没有答案，请如实说"资料中未找到相关信息"。

资料：
{context}

问题：{question}

回答："""

    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
    )

    answer = response.choices[0].message.content
    src_list = ", ".join(set(s["source"] for s in sources))
    return f"{answer}\n\n(参考来源: {src_list})"


# ─── 启动 ───
if __name__ == "__main__":
    # 对 agent_learning 目录建索引
    target_dir = r"D:\agent_learning"
    collection, model = build_index(target_dir)

    print("\n" + "=" * 50)
    print("RAG 知识库就绪！输入问题查询，输入 exit 退出")
    print("=" * 50)

    while True:
        try:
            q = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not q:
            continue
        if q.lower() in ("exit", "quit", "q"):
            break

        print("\n检索中...")
        answer = ask(collection, model, q)
        print(f"\n[回答] {answer}")
