"""
Hello World Agent — 最精简的 ReAct Agent
核心概念：Agent = LLM + 工具 + 循环（思考→行动→观察→再思考）
使用 DeepSeek API
"""
import sys, subprocess

# 修复 Windows GBK 编码问题：强制使用 utf-8
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

# ─── 第一步：定义工具 ───
# Agent 不是"问答"，它能"动手"。工具就是它的手。
# 这里只有一个工具：在终端里执行命令，拿到结果。

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "在终端里执行一条 shell 命令，返回命令的输出结果。用于查看文件、搜索内容、获取系统信息等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "要执行的 shell 命令，例如 ls、cat、find 等。Windows 系统请用 dir、type 等",
                    },
                },
                "required": ["command"],
            },
        },
    }
]


def run_command(command: str) -> str:
    """Agent 实际调用工具时执行的函数"""
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace"
        )
        out = (result.stdout or "") + (result.stderr or "")
        return out if out.strip() else "(命令执行完毕，没有输出)"
    except Exception as e:
        return str(e)


# ─── 第二步：ReAct 循环 ───
# 这是 Agent 的核心：反复 思考→行动→观察→再思考，直到完成任务
# messages 从外部传入，这样多次对话可以共享上下文（Memory）

def run_agent(client: OpenAI, messages: list, max_turns: int = 5):
    for turn in range(max_turns):
        print(f"\n{'='*50}")
        print(f"第 {turn + 1} 轮")

        # 调用 LLM（DeepSeek）
        response = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=1024,
            messages=messages,
            tools=TOOLS,
        )

        choice = response.choices[0]
        msg = choice.message

        # 检查 LLM 的回复：是想用工具，还是纯文字回答？
        if msg.tool_calls:
            # 把 assistant 消息记入历史
            messages.append(msg.model_dump())

            for tool_call in msg.tool_calls:
                import json
                tool_input = json.loads(tool_call.function.arguments)
                print(f"  [行动] 执行命令: {tool_input.get('command')}")

                # 执行工具
                result = run_command(tool_input["command"])
                print(f"  [观察] 结果: {result[:200]}")

                # 把工具执行结果塞回对话历史
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                })
        else:
            # 纯文字回复 → 这轮 ReAct 结束
            print(f"\n[Agent] {msg.content}")
            messages.append({"role": "assistant", "content": msg.content})
            return


# ─── 第三步：对话循环（REPL） ───
if __name__ == "__main__":
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )

    # 对话历史（跨轮持久化 → 这就是 Memory）
    history = []

    print("=" * 50)
    print("Agent 已启动！输入你想做的事，输入 exit 退出")
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

        history.append({"role": "user", "content": user_input})
        run_agent(client, history)
