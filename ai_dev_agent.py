"""
AI Dev Engineer Agent — 综合项目
给它需求，它自己探索代码、定位文件、修改、跑测试、提交 git。

整合了：
- 阶段1：ReAct 循环
- 阶段2：MCP 工具动态发现
- 阶段3：子任务规划（内置）
- 阶段4：RAG 知识库（可选）
- 阶段5-b：记忆管理（长对话不爆 token）
"""
import sys
import json
import os
from dotenv import load_dotenv
load_dotenv()

import asyncio
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from openai import OpenAI
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from memory_manager import MemoryManager
from skill_manager import match_skills

# ─── MCP 工具加载 ───

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


# ─── 系统指令 ───

SYSTEM_PROMPT = """你是一个 AI 开发工程师。用户在维护一个软件项目，给你开发需求。
你必须自主完成：探索代码 → 理解架构 → 定位修改点 → 执行修改 → 验证 → 提交。

## 工作流程（严格遵守顺序）

### 阶段1 — 探索
- 用 list_dir 查看项目目录结构
- 用 grep 搜索相关代码（函数名、类名、关键词）
- 用 read_file 读取关键文件，理解现有代码

### 阶段2 — 规划
- 向用户用 2-3 句话说明你理解的需求
- 列出要修改的文件和修改内容
- 用户确认后再动手（除非用户说"直接做"）

### 阶段3 — 执行
- 用 write_file 修改代码
- 每次只改一个文件，改完确认

### 阶段4 — 验证
- 如果有测试，用 run_command 运行测试
- 测试失败则分析原因、修代码、再跑测试
- 如果没有测试，用 run_command 至少跑一下语法检查（python -m py_compile）

### 阶段5 — 提交
- 用 run_command 执行 git add 和 git commit
- commit message 用中文，格式：类型: 简述
  类型包括：feat（新功能）、fix（修复）、refactor（重构）、test（测试）、docs（文档）

## 原则
- 先读代码再动手，不要猜
- 改最少的文件完成需求
- 编辑文件前先 read_file 确认当前内容
- 出现错误时分析根因，不要盲目重试
- 如果对话中出现了 <Skill> 标记的操作模板，严格按模板的步骤执行
"""


# ─── ReAct 循环 ───

async def run_agent(client: OpenAI, session: ClientSession, messages: list,
                    tools: list, max_turns: int = 15):
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
                    print(f"  [警告] 非法 JSON 参数，跳过")
                    messages.append({
                        "role": "tool", "tool_call_id": tool_call.id,
                        "content": "错误: 参数格式非法",
                    })
                    continue

                # 友好的工具调用展示
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
                preview = result_text[:300]
                if len(result_text) > 300:
                    preview += f"\n... (共 {len(result_text)} 字符)"
                print(f"  📥 结果: {preview}")

                messages.append({
                    "role": "tool", "tool_call_id": tool_call.id,
                    "content": result_text,
                })
        else:
            content = msg.content
            print(f"\n{'='*50}")
            print(f"[AI Dev Engineer]")
            print(content)
            print(f"{'='*50}")
            messages.append({"role": "assistant", "content": content})
            return


# ─── 启动 ───

async def main():
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )

    project_dir = os.getcwd()
    print(f"当前工作目录: {project_dir}")
    print(f"Agent 将在此目录中操作（list_dir、read_file、write_file 等均相对于此）\n")

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
            print("=" * 50)
            print("AI Dev Engineer Agent 已就绪")
            print("输入你的开发需求，输入 exit 退出")
            print("=" * 50)

            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            memory = MemoryManager(max_tokens=8000)  # 开发任务消息更重，token 阈值控制

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

                # 框架层 Skill 匹配（Claude Code 风格：模型感知前注入）
                matched = match_skills(user_input)
                if matched:
                    for skill in matched:
                        tag = f"<Skill name=\"{skill['name']}\">"
                        skill_msg = {
                            "role": "system",
                            "content": f"{tag}\n{skill['content']}\n</Skill>",
                        }
                        messages.append(skill_msg)
                        print(f"  [Skill 注入] {skill['name']}")

                messages.append({"role": "user", "content": user_input})

                if memory.should_compress(messages):
                    old_len = len(messages)
                    # 临时取出 system prompt，避免被送入压缩 LLM
                    sys_msg = messages[0]
                    messages_without_sys = messages[1:]
                    compacted = memory.manage(messages_without_sys)
                    # 恢复：system prompt + 摘要 + 最近 N 条
                    messages = [sys_msg]
                    if compacted[0]["role"] == "system":
                        messages.append(compacted[0])  # 摘要
                        messages.extend(compacted[1:])
                    else:
                        messages.extend(compacted)
                    print(f"  [记忆] 压缩: {old_len} 条 → {len(messages)} 条")

                await run_agent(client, session, messages, tools)


if __name__ == "__main__":
    asyncio.run(main())
