"""
Deep Research Agent — 多步自主调研
核心流程：拆解问题 → 多源搜索(Web+本地) → 追问深挖 → 综合报告
"""
import sys, os, re, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx
from openai import OpenAI
from sentence_transformers import SentenceTransformer
import chromadb


# ═══════════════════════════════════════════════════════
# 搜索层 — 可插拔接口，每个搜索源实现 search(query) → list[dict]
# ═══════════════════════════════════════════════════════

def search_web_bing(query: str, max_results: int = 3) -> list[dict]:
    """Bing 搜索（HTML 抓取，免费无需 API Key）"""
    try:
        resp = httpx.get(
            "https://www.bing.com/search",
            params={"q": query, "count": max_results},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return [{"title": "搜索失败", "body": f"HTTP {resp.status_code}", "href": ""}]

        html = resp.text
        results = []

        # Bing 结果块：<li class="b_algo"> ... </li>
        blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL)

        for block in blocks:
            if len(results) >= max_results:
                break
            # 跳过不含标题链接的伪装块
            if "tilk" not in block and "b_caption" not in block:
                continue

            # 标题：<a class="tilk"> 里的纯文本
            title_m = re.search(r'<a[^>]*class="[^"]*tilk[^"]*"[^>]*>(.*?)</a>', block, re.DOTALL)
            if not title_m:
                title_m = re.search(r'<h2[^>]*>.*?<a[^>]*>(.*?)</a>', block, re.DOTALL)
            title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip() if title_m else ""
            if not title:
                continue

            # 来源链接：提取 Bing 结果中显示的绿色 URL（cite 或 tptt）
            cite_m = re.search(r'<cite[^>]*>(.*?)</cite>', block, re.DOTALL)
            href = re.sub(r'<[^>]+>', '', cite_m.group(1)).strip() if cite_m else ""
            if not href:
                tptt_m = re.search(r'class="tptt"[^>]*>(.*?)</div>', block, re.DOTALL)
                href = re.sub(r'<[^>]+>', '', tptt_m.group(1)).strip() if tptt_m else ""

            # 摘要
            body_m = re.search(r'<(?:p|div) class="[^"]*b_lineclamp[^"]*"[^>]*>(.*?)</(?:p|div)>', block, re.DOTALL)
            if not body_m:
                body_m = re.search(r'class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>', block, re.DOTALL)
            body = re.sub(r'<[^>]+>', '', body_m.group(1)).strip() if body_m else ""
            results.append({"title": title, "body": body, "href": href})

        return results
    except Exception as e:
        return [{"title": "搜索失败", "body": str(e), "href": ""}]


# 本地知识库（懒加载）
_model = None
_collection = None
CHROMA_PATH = os.path.join(os.path.dirname(__file__), ".chroma_db")


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _get_collection():
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        _collection = client.get_collection("agent_knowledge")
    return _collection


def search_local(query: str, top_k: int = 3) -> list[dict]:
    """搜索本地 ChromaDB 知识库"""
    try:
        collection = _get_collection()
        model = _get_model()
        embedding = model.encode([query])[0]
        results = collection.query(query_embeddings=[embedding.tolist()], n_results=top_k)
        if not results["documents"] or not results["documents"][0]:
            return []
        out = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i] if results["metadatas"] else {}
            out.append({"content": doc, "source": meta.get("source", "unknown")})
        return out
    except Exception as e:
        return [{"content": str(e), "source": "error"}]


def search_all(query: str) -> dict:
    """同时对 Web(Bing) 和本地知识库搜索"""
    web = search_web_bing(query)
    local = search_local(query)
    return {"web": web, "local": local}


# ═══════════════════════════════════════════════════════
# LLM 函数 — 全部用 DeepSeek
# ═══════════════════════════════════════════════════════

client = OpenAI(
    api_key="sk-248381b7b8a64de3879fccdfd2f0e213",
    base_url="https://api.deepseek.com",
)


def decompose_question(question: str) -> list[str]:
    """把大问题拆成 3-5 个子问题"""
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": f"""把以下问题拆分成 3-5 个子问题，每个子问题应该具体、可独立研究。
只返回子问题列表，每行一个，以 "- " 开头。

问题：{question}"""}],
        max_tokens=300,
    )
    text = response.choices[0].message.content
    sub_questions = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- "):
            sub_questions.append(line[2:])
    return sub_questions


def assess_and_follow_up(question: str, web_results: list[dict], local_results: list[dict]) -> list[str]:
    """LLM 阅读结果，判断信息是否足够，不够则生成追问"""
    web_text = "\n".join(
        f"[Web] {r['title']}: {r['body'][:200]}" for r in web_results
    ) if web_results else "(Web 搜索无结果)"

    local_text = "\n".join(
        f"[本地] {r['source']}: {r['content'][:200]}" for r in local_results
    ) if local_results else "(本地知识库无结果)"

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": f"""你在调研子问题：
"{question}"

已获取的信息：
{web_text}
{local_text}

评估：
1. 现有信息是否足以回答子问题？
2. 如果不足，生成 1-3 个追问（只返回必要的，以 "- " 开头每行一个）
3. 如果足够，只返回 "SUFFICIENT"

严格按格式返回，不要解释。"""}],
        max_tokens=200,
    )
    text = response.choices[0].message.content
    if "SUFFICIENT" in text:
        return []
    follow_ups = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("- "):
            follow_ups.append(line[2:])
    return follow_ups


def answer_sub_question(question: str, all_materials: list[str]) -> str:
    """综合某子问题的所有材料，给出阶段性回答"""
    materials_text = "\n\n---\n\n".join(all_materials)
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": f"""根据以下调研材料回答子问题。信息不足请如实说明。

子问题：{question}

材料：
{materials_text}

回答（标明来源）："""}],
        max_tokens=512,
    )
    return response.choices[0].message.content


def synthesize(original_question: str, sub_answers: list[dict]) -> str:
    """综合所有子问题结果，生成结构化最终报告"""
    qa_text = "\n\n---\n\n".join(
        f"子问题 {i+1}: {qa['question']}\n阶段性回答: {qa['answer']}"
        for i, qa in enumerate(sub_answers)
    )
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": f"""根据以下调研结果，生成结构化综合报告。

原始问题：{original_question}

调研结果：
{qa_text}

报告格式：
## 概述
（2-3 句话总结核心发现）

## 详细分析
（按主题组织，不按子问题罗列。引用来源。）

## 结论
（1-2 句话收尾。信息不足处标明"待进一步调研"。）"""}],
        max_tokens=1024,
    )
    return response.choices[0].message.content


# ═══════════════════════════════════════════════════════
# Deep Research 核心循环
# ═══════════════════════════════════════════════════════

def deep_research(question: str, max_followup_rounds: int = 2) -> str:
    """主流程：拆解 → 双源搜索 → 追问深挖 → 综合报告"""
    print(f"\n{'='*60}")
    print(f"Deep Research 开始")
    print(f"{'='*60}")

    # 1. 拆解（拆不出来就用原问题本身）
    print("\n[1. 拆解问题]")
    sub_questions = decompose_question(question)
    if not sub_questions:
        print("  (无法拆解，作为原子问题直接调研)")
        sub_questions = [question]
    else:
        for i, q in enumerate(sub_questions):
            print(f"  {i+1}. {q}")

    # 2. 逐个调研
    sub_answers = []
    for i, sq in enumerate(sub_questions):
        print(f"\n{'─'*50}")
        print(f"[2.{i+1} 调研子问题] {sq}")

        all_materials = []
        seen_hrefs = set()  # 避免重复引用

        # 第一轮搜索
        print("  搜索: Bing + 本地知识库...")
        initial = search_all(sq)
        web_count = len([r for r in initial["web"] if r["body"]])
        local_count = len([r for r in initial["local"] if r["content"]])
        print(f"  Bing {web_count} 条, 本地 {local_count} 条")

        for r in initial["web"]:
            if r["href"] and r["href"] not in seen_hrefs:
                seen_hrefs.add(r["href"])
                all_materials.append(f"[Bing: {r['title']}]({r['href']})\n{r['body']}")
        for r in initial["local"]:
            all_materials.append(f"[本地知识库: {r['source']}]\n{r['content']}")

        # 追问循环
        for round_num in range(max_followup_rounds):
            follow_ups = assess_and_follow_up(sq, initial["web"], initial["local"])
            if not follow_ups:
                print("  判断: 信息充分，进入下一子问题")
                break
            print(f"  追问第{round_num+1}轮 ({len(follow_ups)}个):")
            for fq in follow_ups:
                print(f"    → {fq}")
                more = search_all(fq)
                for r in more["web"]:
                    if r["href"] and r["href"] not in seen_hrefs:
                        seen_hrefs.add(r["href"])
                        all_materials.append(f"[Bing: {r['title']}]({r['href']})\n{r['body']}")
                for r in more["local"]:
                    all_materials.append(f"[本地知识库: {r['source']}]\n{r['content']}")

        # 阶段性回答
        print(f"  综合 {len(all_materials)} 份材料, 生成回答...")
        answer = answer_sub_question(sq, all_materials)
        sub_answers.append({"question": sq, "answer": answer, "sources": len(all_materials)})

    # 3. 综合报告
    print(f"\n[3. 综合报告]")
    report = synthesize(question, sub_answers)

    print(f"\n{'='*60}")
    print("调研完成")
    for i, qa in enumerate(sub_answers):
        print(f"  子问题 {i+1}: 引用 {qa['sources']} 份材料")
    print(f"{'='*60}")

    return report


# ═══════════════════════════════════════════════════════
# 启动
# ═══════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("Deep Research Agent")
    print("搜索源: Bing(Web) + ChromaDB(本地知识库)")
    print("流程: 拆解 → 搜索 → 追问 → 综合报告")
    print("=" * 60)
    print("输入复杂问题，输入 exit 退出")

    while True:
        try:
            question = input("\n问题: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见!")
            break

        if not question:
            continue
        if question.lower() in ("exit", "quit", "q"):
            print("再见!")
            break

        report = deep_research(question)
        print(f"\n{'─'*60}")
        print(report)


if __name__ == "__main__":
    main()
