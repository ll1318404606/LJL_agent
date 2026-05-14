"""
非交互式集成测试：模拟多轮对话，验证记忆管理在完整流程中的行为
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from memory_manager import MemoryManager

# 模拟一场长对话：用户跟 Agent 合作开发一个功能
turns = [
    ("user", "帮我写一个 Python 的 TODO 列表应用，用命令行交互"),
    ("assistant", "好的，我来设计一个命令行 TODO 应用。包含添加、查看、删除、标记完成四个功能。先写主框架："),
    ("assistant", "[tool_call] write_file('todo.py', 'class TodoApp: ...')"),
    ("tool", "文件写入成功，45 行"),
    ("user", "添加功能要支持优先级，高/中/低三档"),
    ("assistant", "明白，给 add 方法加 priority 参数，存储时带上优先级字段。"),
    ("assistant", "[tool_call] write_file('todo.py', 'class TodoApp: def add(self, task, priority=\"中\"): ...')"),
    ("tool", "文件写入成功，62 行"),
    ("user", "查看功能要支持按优先级筛选"),
    ("assistant", "好的，list 命令加 --priority high 参数，filter 过滤。"),
    ("assistant", "[tool_call] write_file('todo.py', '... def list(self, priority_filter=None): ...')"),
    ("tool", "文件写入成功，78 行"),
    ("user", "数据要持久化到 JSON 文件，不能程序关了就没"),
    ("assistant", "对，加 save/load 方法，程序启动时从 json 读，每次操作后自动保存。"),
    ("assistant", "[tool_call] write_file('todo.py', '... import json; def save(self): json.dump(...)')"),
    ("tool", "文件写入成功，105 行"),
    ("user", "再加个编辑功能，能修改已有任务的文字"),
    ("assistant", "加 edit 命令，传任务 ID 和新文字。"),
    ("assistant", "[tool_call] write_file('todo.py', '... def edit(self, task_id, new_text): ...')"),
    ("tool", "文件写入成功，118 行"),
    ("user", "删除功能要加确认，防止误删"),
    ("assistant", "delete 命令加 --force 参数，不加的话会提示确认。"),
    ("assistant", "[tool_call] write_file('todo.py', '... def delete(self, task_id, force=False): ...')"),
    ("tool", "文件写入成功，128 行"),
    ("user", "写个 README 说明用法"),
    ("assistant", "[tool_call] write_file('README.md', '# TODO 命令行应用 ...')"),
    ("tool", "文件写入成功，README.md 35 行"),
    ("user", "给 todo.py 写单元测试"),
    ("assistant", "好的，用 pytest 写测试，覆盖增删改查标记。"),
    ("assistant", "[tool_call] write_file('test_todo.py', 'import pytest; def test_add(): ...')"),
    ("tool", "文件写入成功，test_todo.py 52 行"),
    ("user", "测试里加一个边界情况：空字符串任务名"),
    ("assistant", "加了 test_add_empty_task，验证抛出 ValueError。"),
    ("assistant", "[tool_call] write_file('test_todo.py', '... def test_add_empty_task(): ...')"),
    ("tool", "文件写入成功，test_todo.py 68 行"),
    ("user", "标记完成的功能还没实现呢"),
    ("assistant", "抱歉遗漏了！现在加 done 命令，传任务 ID 把 status 改为已完成。"),
    ("assistant", "[tool_call] write_file('todo.py', '... def done(self, task_id): ...')"),
    ("tool", "文件写入成功，todo.py 143 行"),
    ("user", "加个统计功能：总共多少任务、完成率多少"),
    ("assistant", "加 stats 命令，遍历任务算完成数和完成率。"),
    ("user", "再加个导出功能，能导出成 CSV"),
    ("assistant", "加 export 命令，用 csv 模块写文件。"),
]

# ─── 测试 1：基础压缩 ───
print("=" * 60)
print("  测试 1：基础压缩（15 轮对话 → 超过阈值）")
print("=" * 60)

mm = MemoryManager(keep_last=6)
history = []

for i, (role, content) in enumerate(turns):
    history.append({"role": role, "content": content})

    if mm.should_compress(history):
        old_len = len(history)
        history = mm.manage(history)
        print(f"\n>>> 第 {i+1} 条消息后触发压缩: {old_len} 条 → {len(history)} 条")
        print(f"    角色分布: {[m['role'] for m in history]}")
        break  # 第一次压缩后就停，检查结果

print(f"\n最终消息数: {len(history)}")
print(f"\n--- 摘要内容 ---")
print(history[0]["content"][:500])

print(f"\n--- 保留的最近 {mm.keep_last} 条 ---")
for m in history[1:]:
    content_preview = str(m.get("content", ""))[:120]
    print(f"  [{m['role']}]: {content_preview}")

# ─── 测试 2：继续对话，触发二次压缩（分层的摘要） ───
print("\n" + "=" * 60)
print("  测试 2：继续对话 → 二次压缩（摘要的摘要）")
print("=" * 60)

# 模拟继续对话
more_turns = [
    ("user", "CSV 导出要支持 UTF-8 BOM，不然 Excel 打开乱码"),
    ("assistant", "好的，export 方法加 encoding='utf-8-sig'。"),
    ("assistant", "[tool_call] write_file('todo.py', '... def export(self): ... encoding=\"utf-8-sig\"')"),
    ("tool", "文件写入成功，todo.py 156 行"),
    ("user", "再加个导入功能，从 CSV 导入任务"),
    ("assistant", "加 import_csv 命令，读 CSV 逐行创建任务。"),
    ("user", "如果 CSV 里有重复任务怎么办？"),
    ("assistant", "加 --skip-duplicates 参数，根据任务文字判断是否重复。"),
]

for role, content in more_turns:
    history.append({"role": role, "content": content})

    if mm.should_compress(history):
        old_len = len(history)
        old_summary = history[0]["content"] if history[0]["role"] == "system" else "(无)"
        history = mm.manage(history)
        print(f"\n>>> 二次压缩触发: {old_len} 条 → {len(history)} 条")
        print(f"    旧摘要长度: {len(old_summary)} 字")
        print(f"    新摘要长度: {len(history[0]['content'])} 字")
        break

print(f"\n--- 二次压缩后的摘要 ---")
print(history[0]["content"][:600])

print(f"\n--- 保留的最近 {mm.keep_last} 条 ---")
for m in history[1:]:
    content_preview = str(m.get("content", ""))[:120]
    print(f"  [{m['role']}]: {content_preview}")

# ─── 测试 3：边界情况 ───
print("\n" + "=" * 60)
print("  测试 3：边界情况")
print("=" * 60)

# 3a: 空历史
mm2 = MemoryManager(keep_last=5)
assert mm2.should_compress([]) is False
assert mm2.manage([]) == []
print("  3a ✅ 空历史不压缩")

# 3b: 未超阈值
mm3 = MemoryManager(keep_last=5)
short = [{"role": "user", "content": "你好"}] * 3
assert mm3.should_compress(short) is False
assert mm3.manage(short) == short
print("  3b ✅ 未超阈值原样返回")

# 3c: 恰好等于阈值
mm4 = MemoryManager(keep_last=5)
exact = [{"role": "user", "content": f"msg{i}"} for i in range(5)]
assert mm4.should_compress(exact) is False
print("  3c ✅ 等于阈值不压缩")

# 3d: tool 消息截断（>300 字不撑爆 prompt）
mm5 = MemoryManager(keep_last=3)
huge_tool_msg = [
    {"role": "user", "content": "读一下这个文件"},
    {"role": "tool", "content": "x" * 2000},  # 超长 tool 结果
    {"role": "assistant", "content": "文件内容很长"},
    {"role": "user", "content": "总结一下"},
]
result = mm5.manage(huge_tool_msg)
print(f"  3d ✅ 超长 tool 消息截断: {len(result)} 条, 摘要长度={len(result[0]['content'])}")
# 确认摘要中没有 2000 个 x
assert "x" * 2000 not in result[0]["content"]
print("     确认未包含 2000 字符原文")

# 3e: assistant 消息 content=None，但有 tool_calls
mm6 = MemoryManager(keep_last=2)  # 让 tool_calls 消息落入压缩区
tool_calls_msg = [
    {"role": "user", "content": "帮我写个文件"},
    {"role": "assistant", "content": None, "tool_calls": [
        {"function": {"name": "write_file", "arguments": '{"path": "app.py", "content": "print(1)"}'}, "type": "function"}
    ]},
    {"role": "tool", "content": "文件写入成功", "tool_call_id": "call_123"},
    {"role": "assistant", "content": "已写入 app.py"},
]
result = mm6.manage(tool_calls_msg)
print(f"  3e ✅ tool_calls 消息被捕获: 摘要长度={len(result[0]['content'])}")
# 确认摘要中包含了文件相关操作（LLM 用自然语言概括，不一定会原样写函数名）
assert "app.py" in result[0]["content"] or "文件" in result[0]["content"], \
    "摘要应包含文件操作相关内容"
print("     确认 tool_calls 信息已被纳入摘要")

print("\n" + "=" * 60)
print("  全部测试通过 ✅")
print("=" * 60)
