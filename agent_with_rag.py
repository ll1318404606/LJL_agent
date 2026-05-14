"""
Agent + RAG — Agent 可以搜索知识库来回答问题
连接 RAG MCP Server，让 Agent 能"记住"项目文档
"""
import sys, asyncio, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openai import OpenAI
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

TOOLS_CACHE = []


def sanitize_string(text: str) -> str:
    if not text:
        return ""
    return text.encode("utf-8", errors="surrogateescape").decode("utf-8", errors="replace")


async def load_tools(session: ClientSession) -> list[dict]:
    global TOOLS_CACHE
    if TOOLS_CACHE:
        return TOOLS_CACHE
    tools = await session.list_tools()
    for tool in tools.tools:
        TOOLS_CACHE.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": sanitize_string(tool.description or ""),
                "parameters": tool.inputSchema,
            },
        })
    return TOOLS_CACHE


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

        msg = response.choices[0].message

        if msg.tool_calls:
            messages.append(msg.model_dump())
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tool_input = json.loads(tc.function.arguments)
                print(f"  [行动] {tool_name}({tool_input})")

                result = await session.call_tool(tool_name, arguments=tool_input)
                result_text = sanitize_string(result.content[0].text)
                print(f"  [观察] {result_text[:150]}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })
        else:
            print(f"\n[Agent] {msg.content}")
            messages.append({"role": "assistant", "content": msg.content})
            return


async def main():
    client = OpenAI(
        api_key="sk-248381b7b8a64de3879fccdfd2f0e213",
        base_url="https://api.deepseek.com",
    )

    # 连接 RAG MCP Server
    async with stdio_client(
        StdioServerParameters(
            command=r"D:\Python\python.exe",
            args=[r"D:\agent_learning\rag_mcp_server.py"],
        )
    ) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await load_tools(session)
            print(f"已加载 {len(tools)} 个 RAG 工具: {[t['function']['name'] for t in tools]}")
            print("=" * 50)
            print("Agent 已启动！你可以问关于代码库的问题")
            print("=" * 50)

            history = []

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
                await run_agent(client, session, history, tools)


if __name__ == "__main__":
    asyncio.run(main())
