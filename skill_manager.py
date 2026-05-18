"""
Skill 管理器 — 发现、解析、加载 skill 文件
Skill 是存储在 skills/ 目录下的 .md 文件，带 YAML 头部元数据
"""
import os
import re

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """解析 YAML 风格的 frontmatter，返回 (元数据, 正文)"""
    frontmatter = {}
    body = text

    match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
    if match:
        yaml_text = match.group(1)
        body = text[match.end():]

        for line in yaml_text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if key == "triggers":
                    # triggers 在正文中解析为列表
                    continue
                frontmatter[key] = value

        # 解析 triggers（YAML 列表）
        triggers_section = re.search(r'triggers:\s*\n((?:\s*-\s+.+\n?)*)', yaml_text)
        if triggers_section:
            triggers = []
            for t_line in triggers_section.group(1).strip().split("\n"):
                t = t_line.strip().lstrip("-").strip()
                if t:
                    triggers.append(t)
            frontmatter["triggers"] = triggers

    return frontmatter, body


def list_skills() -> list[dict]:
    """列出所有可用 skill 的摘要（名称、描述、触发词）"""
    if not os.path.isdir(SKILLS_DIR):
        return []

    skills = []
    for fname in sorted(os.listdir(SKILLS_DIR)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(SKILLS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            meta, _ = _parse_frontmatter(text)
            skills.append({
                "name": meta.get("name", fname.replace(".md", "")),
                "description": meta.get("description", ""),
                "triggers": meta.get("triggers", []),
                "file": fname,
            })
        except Exception:
            continue

    return skills


def get_skill(name: str) -> str | None:
    """根据名称获取 skill 的完整内容"""
    if not os.path.isdir(SKILLS_DIR):
        return None

    for fname in os.listdir(SKILLS_DIR):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(SKILLS_DIR, fname)
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                text = f.read()
            meta, body = _parse_frontmatter(text)
            skill_name = meta.get("name", fname.replace(".md", ""))
            if skill_name == name:
                return body.strip()
        except Exception:
            continue

    return None


def match_skills(user_text: str) -> list[dict]:
    """框架层匹配：检查用户输入是否包含任何 skill 的触发词。
    返回匹配的 skill 列表，每个包含 name + 完整内容。
    匹配不到则返回空列表。"""
    matched = []
    for skill_meta in list_skills():
        triggers = skill_meta.get("triggers", [])
        if triggers:
            for trigger in triggers:
                if trigger in user_text:
                    content = get_skill(skill_meta["name"])
                    if content:
                        matched.append({
                            "name": skill_meta["name"],
                            "description": skill_meta["description"],
                            "content": content,
                        })
                    break  # 匹配一次就够了，不重复添加
    return matched


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=== 可用 Skills ===\n")
    for s in list_skills():
        triggers_str = ", ".join(s["triggers"])
        print(f"  [{s['name']}]")
        print(f"    描述: {s['description']}")
        print(f"    触发词: {triggers_str}")
        print(f"    文件: {s['file']}")
        print()

    # 测试获取
    print("=== 获取 'add-mcp-tool' ===\n")
    content = get_skill("add-mcp-tool")
    if content:
        print(content[:500])
