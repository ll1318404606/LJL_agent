"""测试 MCP Server 新增工具：grep + run_command + edit_file"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp_server import list_dir, read_file, write_file, grep, run_command, edit_file, glob
import asyncio


async def main():
    base = "D:/agent_learning"

    # 1. grep — 搜索函数定义
    print("=" * 50)
    print("  测试 grep")
    print("=" * 50)

    result = await grep("def compress", base, "*.py")
    print(result[:500])

    # 2. run_command — 语法检查
    print("\n" + "=" * 50)
    print("  测试 run_command")
    print("=" * 50)

    result = await run_command(
        "D:/Python/python.exe -m py_compile D:/agent_learning/memory_manager.py && echo OK",
        cwd=base,
    )
    print(f"语法检查: {result.strip()}")

    # 3. edit_file — 正常编辑
    print("\n" + "=" * 50)
    print("  测试 edit_file")
    print("=" * 50)

    test_file = "D:/agent_learning/test.txt"
    await write_file(test_file, "hello world\nthis is a test\nhello again")

    # 3a: 精确替换
    result = await edit_file(test_file, "hello world", "你好世界")
    print(f"  3a 替换成功: {result}")
    content = await read_file(test_file)
    assert "你好世界" in content, f"应包含'你好世界'，实际: {content[:50]}"
    print(f"     内容: {content.strip()}")

    # 3b: 找不到原字符串
    result = await edit_file(test_file, "nonexistent", "xxx")
    assert "未找到" in result, f"应报未找到，实际: {result}"
    print(f"  3b 未找到报错: {result[:80]}")

    # 3c: 匹配到多处
    await write_file(test_file, "def foo():\n    pass\n\ndef bar():\n    pass\n")
    result = await edit_file(test_file, "pass", "return 1")
    assert "匹配到 2 处" in result, f"应报多处匹配，实际: {result}"
    print(f"  3c 多处匹配报错:\n{result[:200]}")

    # 3d: 用更多上下文使匹配唯一
    result = await edit_file(test_file, "def foo():\n    pass", "def foo():\n    return 1")
    assert "编辑成功" in result, f"应成功，实际: {result}"
    print(f"  3d 上下文唯一化后成功: {result}")

    # 4. glob — 文件模式搜索
    print("\n" + "=" * 50)
    print("  测试 glob")
    print("=" * 50)

    result = await glob("**/*.py", base)
    assert "fibonacci.py" in result, f"应包含 fibonacci.py，实际: {result[:200]}"
    assert "ai_dev_agent.py" in result, f"应包含 ai_dev_agent.py"
    py_count = len(result.split("\n"))
    print(f"  4a 找到 {py_count} 个 .py 文件")
    print(f"     包含 fibonacci.py ✅, ai_dev_agent.py ✅")

    result = await glob("**/*.md", base)
    assert "session_2026-05-10.md" in result
    assert "timsort_explanation.md" in result
    md_count = len(result.split("\n"))
    print(f"  4b 找到 {md_count} 个 .md 文件 ✅")

    result = await glob("**/*.xyz", base)
    assert "未找到" in result
    print(f"  4c 搜索不存在的类型: {result}")

    print("\n" + "=" * 50)
    print("  MCP Server 全部工具测试通过 ✅")
    print(f"  可用工具: list_dir, read_file, write_file, edit_file, grep, glob, run_command")
    print("=" * 50)


asyncio.run(main())
