"""
测试 AI Dev Engineer Agent — 非交互式，模拟用户提需求
用法：直接跑，观察 Agent 如何探索、修改、验证
"""
import sys
import json
import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openai import OpenAI
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

# ─── 用到的辅助函数 ───

def sanitize_string(text: str) -> str:
    return text.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")


async def load_mcp_tools(session: ClientSession) -> list[dict]:
    tools = await session.list_tools()
    openai_tools = []
    for tool in tools.tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": sanitize_string(tool.description or ""),
                "parameters": tool.inputSchema,
            },
        })
    return openai_tools


SYSTEM_PROMPT = """你是一个 AI 开发工程师。用户在维护一个软件项目，给你开发需求。
你必须自主完成：探索代码 → 理解架构 → 定位修改点 → 执行修改 → 验证 → 提交。

## 工作流程

1. 探索：用 list_dir、grep、read_file 了解项目结构和代码
2. 规划：向用户说明你理解的需求和修改方案
3. 执行：用 write_file 修改代码
4. 验证：用 run_command 跑测试或语法检查
5. 提交：用 run_command 执行 git add + git commit

## 原则
- 先读代码再动手
- 改最少的文件
- 出错了分析根因"""


async def run_agent(client, session, messages, tools, max_turns=15):
    for turn in range(max_turns):
        print(f"\n{'─'*50}")
        print(f"第 {turn + 1} 轮")

        response = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=2048,
            messages=messages,
            tools=tools,
        )

        choice = response.choices[0]
        msg = choice.message

        if msg.tool_calls:
            messages.append(msg.model_dump())

            for tool_call in msg.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_input = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    messages.append({
                        "role": "tool", "tool_call_id": tool_call.id,
                        "content": "错误: 参数格式非法",
                    })
                    continue

                if tool_name == "read_file":
                    print(f"  📖 读取: {tool_input.get('path', '?')}")
                elif tool_name == "write_file":
                    print(f"  ✏️  写入: {tool_input.get('path', '?')}")
                elif tool_name == "list_dir":
                    print(f"  📂 列出: {tool_input.get('path', '?')}")
                elif tool_name == "grep":
                    print(f"  🔍 搜索: '{tool_input.get('pattern', '?')}'")
                elif tool_name == "run_command":
                    cmd = str(tool_input.get('command', ''))[:80]
                    print(f"  ⚡ 执行: {cmd}")
                else:
                    print(f"  🔧 调用: {tool_name}")

                result = await session.call_tool(tool_name, arguments=tool_input)
                result_text = sanitize_string(result.content[0].text)
                preview = result_text[:400]
                if len(result_text) > 400:
                    preview += f"\n... (共 {len(result_text)} 字符)"
                print(f"  📥 结果: {preview}")

                messages.append({
                    "role": "tool", "tool_call_id": tool_call.id,
                    "content": result_text,
                })
        else:
            print(f"\n[AI Dev Engineer]\n{msg.content}")
            messages.append({"role": "assistant", "content": msg.content})
            return


async def main():
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )

    test_dir = "D:/agent_learning"
    user_request = "给 fibonacci.py 里的 fibonacci 函数加一个 lru_cache 缓存装饰器，能缓存最近 128 个计算结果"

    print("=" * 60)
    print("AI Dev Engineer Agent — 自动化测试")
    print("=" * 60)
    print(f"项目目录: {test_dir}")
    print(f"用户需求: {user_request}")
    print("=" * 60)

    async with stdio_client(
        StdioServerParameters(
            command="D:\\Python\\python.exe",
            args=["D:\\agent_learning\\mcp_server.py"],
        )
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_mcp_tools(session)
            print(f"已加载 {len(tools)} 个工具: {[t['function']['name'] for t in tools]}")

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_request},
            ]

            await run_agent(client, session, messages, tools)

    # 展示最终结果
    print("\n" + "=" * 60)
    print("Agent 执行完毕。验证修改结果：")
    print("=" * 60)
    with open("D:/agent_learning/fibonacci.py", "r", encoding="utf-8") as f:
        content = f.read()
    if "lru_cache" in content:
        print("✅ fibonacci.py 中已包含 lru_cache")
        # 找到相关行
        for i, line in enumerate(content.split("\n"), 1):
            if "lru_cache" in line or "functools" in line or "cache" in line.lower():
                print(f"  L{i}: {line.strip()}")
    else:
        print("❌ fibonacci.py 中未找到 lru_cache — Agent 可能没有成功修改")


if __name__ == "__main__":
    asyncio.run(main())
