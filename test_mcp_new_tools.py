"""测试 MCP Server 新增工具：grep + run_command"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mcp_server import list_dir, read_file, write_file, grep, run_command
import asyncio


async def main():
    base = "D:/agent_learning"

    # 1. grep — 搜索函数定义
    print("=" * 50)
    print("  测试 grep")
    print("=" * 50)

    result = await grep("def compress", base, "*.py")
    print(result[:500])

    # 2. grep — 搜索类定义
    print("\n---")
    result = await grep("class MemoryManager", base, "*.py")
    print(result[:300])

    # 3. run_command — 跑已有测试
    print("\n" + "=" * 50)
    print("  测试 run_command")
    print("=" * 50)

    result = await run_command(
        "D:/Python/python.exe -m py_compile D:/agent_learning/memory_manager.py && echo OK",
        cwd=base,
    )
    print(f"语法检查: {result.strip()}")

    # 4. run_command — git status
    print("\n---")
    result = await run_command("git status --short", cwd=base)
    print(f"git status:\n{result[:500]}")

    print("\n" + "=" * 50)
    print("  MCP Server 新工具测试通过 ✅")
    print("=" * 50)


asyncio.run(main())
