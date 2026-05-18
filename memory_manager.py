"""
记忆管理模块 — 自动压缩旧对话
- Token 级阈值（非消息条数）
- 分层再压缩（摘要的摘要）
- 重要性分级截断（极端场景兜底）
"""
import os
import re
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI


def estimate_tokens(messages: list) -> int:
    """粗略估算消息列表的 token 数（中英文混合场景，~3 字/token）"""
    total = 0
    for m in messages:
        text = str(m.get("content", ""))
        if not text:
            tcs = m.get("tool_calls")
            if tcs:
                text = str(tcs)
        total += len(text) // 3
    return total


class MemoryManager:
    """
    管理对话历史的 token 消耗。
    - max_tokens: token 阈值，超限触发压缩
    - 分层摘要：检测旧摘要层级，递增标记（L1 → L2 → L3...）
    - 极端情况按重要性截断
    """

    DEFAULT_MAX_TOKENS = 8000

    def __init__(self, max_tokens: int = None, api_key: str = None,
                 base_url: str = "https://api.deepseek.com"):
        self.max_tokens = max_tokens or self.DEFAULT_MAX_TOKENS
        self.client = OpenAI(
            api_key=api_key or os.getenv("DEEPSEEK_API_KEY"),
            base_url=base_url,
        )

    # ─── 判断 ────────────────────────────────────

    def should_compress(self, messages: list) -> bool:
        """按 token 数判断是否需要压缩"""
        return estimate_tokens(messages) > self.max_tokens

    # ─── 压缩 ────────────────────────────────────

    def compress(self, old_messages: list, current_layer: int = 0) -> tuple[str, int]:
        """
        用 LLM 把旧消息压成一段摘要。
        返回 (摘要文本, 新层级编号)。
        """
        if not old_messages:
            return "", current_layer

        transcript = []
        for m in old_messages:
            role = m.get("role", "?")
            content = m.get("content", "")
            if content:
                if role == "tool" and len(str(content)) > 300:
                    content = str(content)[:300] + "..."
                # 旧的系统摘要会被再压缩，展平展示避免嵌套标签
                if role == "system" and re.search(r'<对话背景摘要|<L\d+摘要>', str(content)):
                    inner = re.sub(r'<[^>]+>', '', str(content)).strip()
                    transcript.append(f"[历史摘要]: {inner[:200]}")
                    continue
                transcript.append(f"[{role}]: {content}")
            elif role == "assistant" and m.get("tool_calls"):
                tcs = m["tool_calls"]
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

        layer_hint = f"这是第{current_layer}层摘要的再压缩。" if current_layer > 0 else ""

        prompt = f"""请将以下对话历史压缩成一段简洁的摘要（不超过 300 字）。
{layer_hint}
保留：用户的核心需求、做出的决定、重要的代码改动、待解决的问题。

对话历史：
{history_text}

摘要："""

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        new_layer = current_layer + 1
        return response.choices[0].message.content.strip(), new_layer

    # ─── 层级检测 ────────────────────────────────

    def _detect_summary_layer(self, messages: list) -> int:
        """检测消息列表中已有摘要的最高层级"""
        max_layer = 0
        for m in messages:
            if m.get("role") == "system":
                content = str(m.get("content", ""))
                match = re.search(r'<L(\d+)摘要>', content)
                if match:
                    max_layer = max(max_layer, int(match.group(1)))
        return max_layer

    # ─── 主入口 ──────────────────────────────────

    def manage(self, messages: list) -> list:
        """
        检查 token 消耗，必要时压缩。
        1. 从尾部找切分点（保留最近消息在 token 阈值 70% 内）
        2. 检测已有摘要层级，递增再压缩
        3. 压缩后仍超限 → 分级截断
        """
        if not self.should_compress(messages):
            return messages

        # 从尾往前找切分点
        split_idx = len(messages)
        running_tokens = 0
        for i in range(len(messages) - 1, -1, -1):
            msg_tokens = estimate_tokens([messages[i]])
            if running_tokens + msg_tokens > self.max_tokens * 0.7:
                split_idx = i + 1
                break
            running_tokens += msg_tokens
        else:
            split_idx = 0

        old_part = messages[:split_idx]
        recent_part = messages[split_idx:]

        if not old_part:
            return self._priority_truncate(messages)

        current_layer = self._detect_summary_layer(old_part)
        summary, new_layer = self.compress(old_part, current_layer)

        tag = f"L{new_layer}摘要"
        compact = [{"role": "system", "content": f"<对话背景摘要 {tag}>\n{summary}\n</对话背景摘要>"}]
        compact.extend(recent_part)

        # 压缩后仍超限 → 分级截断
        if self.should_compress(compact):
            return self._priority_truncate(compact)

        return compact

    # ─── 分级截断 ────────────────────────────────

    def _priority_truncate(self, messages: list) -> list:
        """
        按重要性丢弃消息，直到回到 token 阈值内。
        保留优先级：system prompt > 最近原文 > 工具调用 > 旧摘要 > 旧工具输出
        """
        PRIORITY = {
            "system_prompt": 1,
            "recent_user": 2,
            "recent_assistant": 3,
            "tool_call": 4,
            "summary": 5,
            "tool_result": 6,
        }

        scored = []
        for i, m in enumerate(messages):
            role = m.get("role", "")
            content = str(m.get("content", ""))
            closeness = len(messages) - i  # 位置分值，越靠后越大

            if role == "system" and re.search(r'<(?:对话背景摘要|L\d+摘要)>', content):
                priority = PRIORITY["summary"]
            elif role == "system":
                priority = PRIORITY["system_prompt"]
            elif role == "user":
                priority = PRIORITY["recent_user"]
            elif role == "assistant" and m.get("tool_calls"):
                priority = PRIORITY["tool_call"]
            elif role == "assistant":
                priority = PRIORITY["recent_assistant"]
            elif role == "tool":
                priority = PRIORITY["tool_result"]
            else:
                priority = 5

            score = priority * 100 - closeness  # 越低越重要
            scored.append((score, i, m))

        scored.sort(key=lambda x: x[0])

        keep = set(range(len(messages)))
        for score, idx, m in reversed(scored):
            if not self.should_compress([messages[i] for i in sorted(keep)]):
                break
            keep.discard(idx)

        return [messages[i] for i in sorted(keep)]


# ─── 无 LLM 版本的截断（轻量备选）────────────────────

def simple_truncate(messages: list, max_tokens: int = 8000) -> list:
    """
    不加摘要，从旧到新直接丢弃，直到 token 数达标。
    适合不想消耗额外 LLM token 的场景。
    """
    while estimate_tokens(messages) > max_tokens and len(messages) > 1:
        dropped = messages.pop(0)
        role = dropped.get("role", "?")
        content_preview = str(dropped.get("content", ""))[:60]
        print(f"  [截断] 丢弃 {role} 消息: {content_preview}...")
    return messages
