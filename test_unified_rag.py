"""快速测试统一 RAG 检索"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from unified_rag import build_unified_index, search

target_dir = r"D:\agent_learning"
collection, model = build_unified_index(target_dir)

if collection is None:
    print("索引构建失败!")
    sys.exit(1)

# 测试用例：(查询, 期望来源类型)
tests = [
    ("MCP 协议怎么做工具发现？", "document", "all"),
    ("delegate_sub_agent 是做什么的？", "code", "all"),
    ("什么是 RAG？", "document", "all"),
    ("FastMCP 怎么用？", "document", "all"),
    ("search_knowledge 函数怎么实现的？", "code", "all"),
]

print("\n" + "=" * 55)
print("  检索测试")
print("=" * 55)

for query, expected_type, scope in tests:
    print(f"\n{'─' * 45}")
    print(f"查询: {query}")
    print(f"范围: {scope}")
    chunks, metas = search(collection, model, query, top_k=3, filter_type=scope)

    if not chunks:
        print("  ❌ 无结果")
        continue

    # 检查是否有期望类型的来源
    found_expected = any(m["doc_type"] == expected_type for m in metas)
    status = "✅" if found_expected else "⚠️"
    print(f"  {status} 命中 {len(chunks)} 个结果:")
    for i, (c, m) in enumerate(zip(chunks, metas)):
        t = m["doc_type"]
        icon = "💻" if t == "code" else "📄"
        src = m["source"]
        elem = m.get("elem_or_section", "")
        print(f"      [{i+1}] {icon} [{t}] {src} | {elem}")

# 测试按类型过滤
print(f"\n{'─' * 45}")
print("过滤测试: 仅代码")
chunks, metas = search(collection, model, "协议", top_k=3, filter_type="code")
if chunks:
    types = set(m["doc_type"] for m in metas)
    print(f"  ✅ 全部是代码块 (types found: {types})" if types == {"code"} else f"  ❌ 混入了其他类型: {types}")
else:
    print("  (无代码结果)")

print(f"\n过滤测试: 仅文档")
chunks, metas = search(collection, model, "协议", top_k=3, filter_type="document")
if chunks:
    types = set(m["doc_type"] for m in metas)
    print(f"  ✅ 全部是文档块 (types found: {types})" if types == {"document"} else f"  ❌ 混入了其他类型: {types}")
else:
    print("  (无文档结果)")

print("\n=== 测试完成 ===")
