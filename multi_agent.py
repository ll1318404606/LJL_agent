"""
Multi-Agent 系统 — Manager 不做具体活，而是委派给子 Agent
核心概念：委派（Delegate）、子 Agent 独立的 ReAct 循环、状态汇总
"""
import sys, asyncio, json, os
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openai import OpenAI
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession


def sanitize_string(text: str) -> str:
    return text.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")


# ─── 子 Agent ────────────────────────────────────────
# 子 Agent 有自己的 ReAct 循环，有独立的对话上下文
# 但工具池比 Manager 少 —— 只给它完成任务需要的工具

async def sub_agent(client: OpenAI, session: ClientSession, task: str, max_turns: int = 3) -> str:
    """启动一个子 Agent，执行单一任务，返回结果"""
    print(f"\n  [子Agent 启动] 任务: {task[:80]}")
    messages = [{
        "role": "system",
        "content": "你是一个执行单一任务的子 Agent。用工具完成任务，然后直接返回结果。不要多轮对话。"
    }, {
        "role": "user",
        "content": task,
    }]

    # 子 Agent 只用 MCP 工具（list_dir, read_file, write_file）
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

    for turn in range(max_turns):
        print(f"  [子Agent 第{turn+1}轮]")

        response = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=512,
            messages=messages,
            tools=openai_tools,
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg.model_dump())
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tool_input = json.loads(tc.function.arguments)
                print(f"  [子Agent 行动] {tool_name}({tool_input})")
                result = await session.call_tool(tool_name, arguments=tool_input)
                result_text = sanitize_string(result.content[0].text)
                print(f"  [子Agent 结果] {result_text[:100]}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })
        else:
            print(f"  [子Agent 完成] {msg.content[:80]}")
            return msg.content

    return "子 Agent 达到最大轮数，未能完成任务"


# ─── Manager Agent ────────────────────────────────────
# Manager 不调用具体工具，它只有一个能力：委派子 Agent

MANAGER_SYSTEM = """你是一个 Manager Agent，负责协调子 Agent 完成任务。

你有两个子 Agent 可以委派：
- explorer: 用来列出目录、查找文件
- reader: 用来读取文件内容
- writer: 用来创建或修改文件

规则：
1. 收到用户任务后，先分析需要哪些子 Agent
2. 逐步委派（一次一个），根据上一步的结果决定下一步
3. 最后汇总所有子 Agent 的结果，给用户一个完整答案
4. 委派给子 Agent 的任务必须描述清楚：做什么、参数是什么"""


async def manager_loop(client: OpenAI, session: ClientSession, user_request: str, max_turns: int = 5):
    """Manager 的 ReAct 循环"""
    # 构建 Manager 专用工具：委派子 Agent
    manager_tools = [{
        "type": "function",
        "function": {
            "name": "delegate_sub_agent",
            "description": "委派任务给子 Agent。agent_type 可选: explorer(探索文件), reader(读取文件), writer(写入文件)。task 是给子 Agent 的具体任务描述，必须包含具体参数。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "给子 Agent 的具体任务，包含路径、文件名等参数"},
                    "agent_type": {"type": "string", "enum": ["explorer", "reader", "writer"]},
                },
                "required": ["task", "agent_type"],
            },
        },
    }]

    messages = [{"role": "system", "content": MANAGER_SYSTEM}, {"role": "user", "content": user_request}]

    for turn in range(max_turns):
        print(f"\n{'='*50}")
        print(f"[Manager 第{turn+1}轮]")

        response = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=1024,
            messages=messages,
            tools=manager_tools,
        )

        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg.model_dump())
            for tc in msg.tool_calls:
                tool_input = json.loads(tc.function.arguments)
                task = tool_input["task"]
                agent_type = tool_input["agent_type"]
                print(f"\n>>> Manager 委派 {agent_type}: {task[:80]}")

                # 启动子 Agent！子 Agent 有自己的 ReAct 循环
                sub_result = await sub_agent(client, session, task)
                print(f"<<< {agent_type} 返回: {sub_result[:100]}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": f"[{agent_type}] {sub_result}",
                })
        else:
            print(f"\n[Manager 回答] {msg.content}")
            messages.append({"role": "assistant", "content": msg.content})
            return


# ─── 启动 ───
async def main():
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )

    async with stdio_client(
        StdioServerParameters(
            command=r"D:\Python\python.exe",
            args=[r"D:\agent_learning\mcp_server.py"],
        )
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("Manager Agent 已启动（带 explorer / reader / writer 子Agent）")
            print("=" * 50)

            while True:
                try:
                    user_input = input("\n你: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n再见！")
                    break

                if not user_input:
                    continue
                if user_input.lower() in ("exit", "quit", "q"):
                    print("再见！")
                    break

                await manager_loop(client, session, user_input)
