"""
长文本处理管线 — 串联分块 + 记忆管理 + 深度研究
chunkers → unified_rag → memory_manager → (deep_research)
"""
import sys, os
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import chromadb
from sentence_transformers import SentenceTransformer
from openai import OpenAI

import chunkers
from memory_manager import MemoryManager
from deep_research import deep_research as _deep_research_agent


class LongTextPipeline:
    """
    长文本处理管线。
    1. ingest()    — 分块 + 建向量索引
    2. chat()      — 多轮 RAG 问答 + 记忆压缩
    3. research()  — 复杂问题深度研究（Bing + 本地）
    """

    def __init__(self, chroma_dir: str = None, max_tokens: int = 8000):
        self.chroma_dir = chroma_dir or os.path.join(
            os.path.dirname(__file__), ".chroma_db"
        )
        self.memory = MemoryManager(max_tokens=max_tokens)
        self.collection = None
        self.model = None
        self.messages = []
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )

    # ─── 1. 摄入 ──────────────────────────────────

    def ingest(self, directory: str) -> dict:
        """扫描目录 → 分块 → 向量化 → 存入 ChromaDB"""
        print(f"扫描并分块: {directory}")
        all_chunks, stats = chunkers.chunk_directory(directory)

        if not all_chunks:
            return {"error": "无内容"}

        print(f"代码 {stats['code_chunks']} 块, 文档 {stats['doc_chunks']} 块")

        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        print("向量化...")
        texts = [c["content"] for c in all_chunks]
        embeddings = self.model.encode(texts, show_progress_bar=True)

        # 存入 ChromaDB
        chroma_client = chromadb.PersistentClient(path=self.chroma_dir)
        self.collection = chroma_client.get_or_create_collection(
            "long_text_pipeline"
        )
        # 清空旧索引
        try:
            existing = self.collection.get()
            if existing["ids"]:
                self.collection.delete(ids=existing["ids"])
        except Exception:
            pass

        batch_size = 100
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]
            self.collection.add(
                ids=[c["id"] for c in batch],
                documents=[c["content"] for c in batch],
                embeddings=embeddings[i:i + batch_size].tolist(),
                metadatas=[{
                    "doc_type": c["doc_type"],
                    "source": c["source"],
                    "elem_or_section": c.get("element") or c.get("section") or "",
                } for c in batch],
            )

        stats["indexed"] = len(all_chunks)
        print(f"索引: {len(all_chunks)} 块 → {self.chroma_dir}")
        return stats

    # ─── 2. 检索 ──────────────────────────────────

    def _search(self, query: str, top_k: int = 3,
                filter_type: str = "all") -> tuple[list, list]:
        """搜索向量索引，返回 (chunks, metas)"""
        if self.collection is None or self.model is None:
            return [], []

        q_emb = self.model.encode([query])[0]

        where = None
        if filter_type == "code":
            where = {"doc_type": "code"}
        elif filter_type == "document":
            where = {"doc_type": "document"}

        results = self.collection.query(
            query_embeddings=[q_emb.tolist()],
            n_results=top_k,
            where=where,
        )

        if not results["documents"] or not results["documents"][0]:
            return [], []

        chunks = results["documents"][0]
        metas = results["metadatas"][0] if results["metadatas"] else []
        return chunks, metas

    # ─── 3. 对话 ──────────────────────────────────

    def chat(self, question: str, filter_type: str = "all") -> str:
        """
        单轮 RAG 问答。
        - 检索相关块 → 拼 prompt → LLM 回答
        - 对话历史由 memory_manager 自动压缩
        """
        chunks, metas = self._search(question, filter_type=filter_type)

        if not chunks:
            answer = "(知识库中无相关内容)"
        else:
            parts = []
            for i, (chunk, meta) in enumerate(zip(chunks, metas)):
                t = "文档" if meta.get("doc_type") == "document" else "代码"
                src = meta.get("source", "?")
                elem = meta.get("elem_or_section", "")
                label = f"[{t}] {src}"
                if elem:
                    label += f" | {elem}"
                parts.append(f"{label}\n{chunk}")

            context = "\n\n---\n\n".join(parts)
            prompt = f"""根据以下资料回答问题。找不到就说"未找到相关信息"。

资料：
{context}

问题：{question}

回答："""

            self.messages.append({"role": "user", "content": question})

            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=self.messages + [{"role": "user", "content": prompt}],
                max_tokens=512,
            )
            answer = response.choices[0].message.content

            self.messages.append({"role": "assistant", "content": answer})

        # 记忆管理
        if self.memory.should_compress(self.messages):
            before = len(self.messages)
            self.messages = self.memory.manage(self.messages)
            after = len(self.messages)
            print(f"  [记忆压缩] {before} → {after} 条消息")

        return answer

    # ─── 4. 深度研究 ──────────────────────────────

    def research(self, question: str) -> str:
        """复杂问题走深度研究回路"""
        return _deep_research_agent(question)

    # ─── 5. 交互入口 ──────────────────────────────

    def run(self, directory: str = None):
        """交互式对话循环"""
        if directory:
            self.ingest(directory)

        print("=" * 55)
        print("长文本处理管线")
        print("  chat 问答 | research 深度研究 | exit 退出")
        if self.collection:
            print(f"  索引: {self.collection.count()} 块")
        print("=" * 55)

        while True:
            try:
                raw = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n结束")
                break

            if not raw:
                continue
            if raw.lower() in ("exit", "quit", "q"):
                break

            # 模式判断
            if raw.lower().startswith("research:") or raw.lower().startswith("深研:"):
                q = raw.split(":", 1)[1].strip()
                if q:
                    report = self.research(q)
                    print(f"\n{report}")
                else:
                    print("请输入研究问题，如: research: MCP 协议和 HTTP API 怎么选")
                continue

            # 默认 chat
            answer = self.chat(raw)
            print(f"\n{answer}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="长文本处理管线")
    p.add_argument("--ingest", "-i", help="要摄入的目录路径")
    p.add_argument("--chat", "-c", help="直接问答（不进入交互模式）")
    p.add_argument("--research", "-r", help="深度研究问题")
    p.add_argument("--max-tokens", "-t", type=int, default=8000,
                   help="记忆压缩 token 阈值 (默认 8000)")
    args = p.parse_args()

    pipeline = LongTextPipeline(max_tokens=args.max_tokens)

    if args.ingest:
        pipeline.ingest(args.ingest)

    if args.research:
        print(pipeline.research(args.research))
    elif args.chat:
        print(pipeline.chat(args.chat))
    else:
        pipeline.run()
