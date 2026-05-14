"""测试记忆管理模块"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from memory_manager import MemoryManager

# 模拟一段长对话
messages = [
    {"role": "user", "content": "帮我写一个计算斐波那契数列的 Python 函数"},
    {"role": "assistant", "content": "好的，这是一个递归实现：def fib(n): ..."},
    {"role": "user", "content": "改成迭代版本，递归太慢了"},
    {"role": "assistant", "content": "已改为迭代版本，使用 while 循环..."},
    {"role": "user", "content": "现在把这个函数加到文件 my_math.py 里"},
    {"role": "assistant", "tool_calls": "write_file('my_math.py', ...)"},
    {"role": "tool", "content": "文件写入成功"},
    {"role": "assistant", "content": "已将 fib 函数写入 my_math.py"},
    {"role": "user", "content": "再加一个判断质数的函数"},
    {"role": "assistant", "content": "好的，is_prime 函数：def is_prime(n): ..."},
    {"role": "user", "content": "两个函数都加个类型注解"},
    {"role": "assistant", "content": "已添加类型注解..."},
    {"role": "user", "content": "写个单元测试"},
]

mm = MemoryManager(keep_last=5)

print(f"原始消息数: {len(messages)}")
print(f"保留最近: {mm.keep_last} 条")
print(f"需要压缩: {mm.should_compress(messages)}")

print("\n" + "=" * 50)
print("  执行压缩...")
print("=" * 50)

compact = mm.manage(messages)

print(f"\n压缩后消息数: {len(compact)}")
print(f"消息角色分布: {[m['role'] for m in compact]}")

print("\n--- 摘要内容 ---")
print(compact[0]["content"])

print("\n--- 保留的最近 5 条原文 ---")
for i, m in enumerate(compact[1:]):
    content_preview = str(m.get("content", ""))[:100]
    print(f"  [{m['role']}]: {content_preview}...")
