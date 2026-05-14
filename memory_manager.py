"""
记忆管理模块 — 自动压缩旧对话
当 messages 超过阈值时，用 LLM 把旧消息压成摘要，保留最近 N 条原文
"""
from openai import OpenAI


class MemoryManager:
    """
    管理对话历史的 token 消耗。
    - keep_last: 保留最近 N 条消息原文
    - 超出部分用 LLM 压缩成摘要，作为 system 消息插入
    """

    def __init__(self, keep_last: int = 10, api_key: str = None,
                 base_url: str = "https://api.deepseek.com"):
        self.keep_last = keep_last
        self.client = OpenAI(
            api_key=api_key or "sk-248381b7b8a64de3879fccdfd2f0e213",
            base_url=base_url,
        )

    def compress(self, old_messages: list) -> str:
        """用 LLM 把旧消息压成一段摘要"""
        if not old_messages:
            return ""

        # 把消息列表序列化成可读文本
        transcript = []
        for m in old_messages:
            role = m.get("role", "?")
            content = m.get("content", "")
            if content:
                # tool 消息截断一下
                if role == "tool" and len(str(content)) > 300:
                    content = str(content)[:300] + "..."
                transcript.append(f"[{role}]: {content}")
            elif role == "assistant" and m.get("tool_calls"):
                # assistant 消息可能没有文字，只有 tool_calls 声明
                tcs = m["tool_calls"]
                # 兼容两种格式：OpenAI 标准 [{function: {name, arguments}}] 或简化的字符串
                if isinstance(tcs, list):
                    for tc in tcs:
                        if isinstance(tc, dict):
                            fn = tc.get("function", {})
                            name = fn.get("name", "?")
                            args = str(fn.get("arguments", ""))[:200]
                        else:
                            name = str(tc)
                            args = ""
                        transcript.append(f"[assistant → tool_call]: {name}({args})")
                elif isinstance(tcs, str):
                    transcript.append(f"[assistant → tool_call]: {tcs[:300]}")

        history_text = "\n".join(transcript)

        prompt = f"""请将以下对话历史压缩成一段简洁的摘要（不超过 300 字）。
保留：用户的核心需求、做出的决定、重要的代码改动、待解决的问题。

对话历史：
{history_text}

摘要："""

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,  # 低温度，确保稳定输出
        )
        return response.choices[0].message.content.strip()

    def manage(self, messages: list) -> list:
        """
        检查消息量，必要时压缩。
        返回处理后的消息列表。
        """
        if len(messages) <= self.keep_last:
            return messages

        # 切分：旧消息 vs 最近 N 条
        old_part = messages[:-self.keep_last]
        recent_part = messages[-self.keep_last:]

        # 检查是否已有摘要，有则合并到旧消息中一起再压缩
        summary = self.compress(old_part)

        # 重新组装：[system: 摘要] + [最近 N 条原文]
        compact = [{"role": "system", "content": f"<对话背景摘要>\n{summary}\n</对话背景摘要>"}]
        compact.extend(recent_part)

        return compact

    def should_compress(self, messages: list) -> bool:
        """是否需要压缩"""
        return len(messages) > self.keep_last


# ─── 无 LLM 版本的摘要（轻量备选）────────────────────

def simple_compress(messages: list, keep_last: int = 10) -> list:
    """
    不带摘要的简单策略：直接丢弃旧消息，只保留最近 N 条。
    适合不想消耗额外 token 的场景。
    """
    if len(messages) <= keep_last:
        return messages
    dropped_count = len(messages) - keep_last
    print(f"  [记忆] 已丢弃 {dropped_count} 条旧消息")
    return messages[-keep_last:]
