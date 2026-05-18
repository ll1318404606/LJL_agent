"""
Agent with MCP — 工具不再写死在代码里，而是通过 MCP Server 动态发现
"""
import sys, asyncio, json, os
from dotenv import load_dotenv
load_dotenv()
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openai import OpenAI
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from memory_manager import MemoryManager

# ─── 第一步：从 MCP Server 获取工具并转换成 OpenAI 格式 ───

def sanitize_string(text: str) -> str:
    """清除字符串中的 surrogate 字符和乱码"""
    return text.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")


def sanitize_tools(tools: list[dict]) -> list[dict]:
    """递归清除 tools 列表中所有的 surrogate 字符"""
    raw = json.dumps(tools, ensure_ascii=False)
    import re
    # 移除 lone surrogates
    raw = re.sub(r'\\ud[89a-fA-F][0-9a-fA-F]{2}', '', raw)
    return json.loads(raw)


async def load_mcp_tools(session: ClientSession) -> list[dict]:
    """连接 MCP Server，获取它提供的工具列表，转成 OpenAI 兼容格式"""
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
    return sanitize_tools(openai_tools)


# ─── 第二步：ReAct 循环（跟 hello_agent.py 结构一样） ───

async def run_agent(client: OpenAI, session: ClientSession, messages: list, tools: list, max_turns: int = 5):
    for turn in range(max_turns):
        print(f"\n{'='*50}")
        print(f"第 {turn + 1} 轮")

        response = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=1024,
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
                    print(f"  [警告] DeepSeek 生成非法 JSON，跳过: {str(tool_call.function.arguments)[:200]}")
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": "错误: 参数格式非法，请重新调用",
                    })
                    continue
                print(f"  [行动] 调用 MCP 工具: {tool_name}({tool_input})")

                # 关键变化：工具调用走 MCP Session，而不是本地函数
                result = await session.call_tool(tool_name, arguments=tool_input)
                result_text = sanitize_string(result.content[0].text)
                print(f"  [观察] 结果: {result_text[:200]}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_text,
                })
        else:
            print(f"\n[Agent] {msg.content}")
            messages.append({"role": "assistant", "content": msg.content})
            return


# ─── 第三步：启动 ───

async def main():
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )

    # 启动 MCP Server（作为子进程），建立连接
    async with stdio_client(
        StdioServerParameters(
            command="D:\\Python\\python.exe",
            args=["D:\\agent_learning\\mcp_server.py"],
        )
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 从 MCP Server 动态获取工具列表
            tools = await load_mcp_tools(session)
            print(f"已加载 {len(tools)} 个工具: {[t['function']['name'] for t in tools]}")
            print("=" * 50)
            print("Agent 已启动！输入你想做的事，输入 exit 退出")
            print("=" * 50)

            history = []
            memory = MemoryManager(keep_last=10)

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

                history.append({"role": "user", "content": user_input})

                # 记忆管理：消息过多时自动压缩旧对话
                if memory.should_compress(history):
                    old_len = len(history)
                    history = memory.manage(history)
                    print(f"  [记忆] 压缩完成: {old_len} 条 → {len(history)} 条")

                await run_agent(client, session, history, tools)


if __name__ == "__main__":
    asyncio.run(main())
