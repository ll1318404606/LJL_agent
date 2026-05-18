"""
MCP Server — 文件系统 + 代码搜索 + 命令执行 + Skill 管理
独立进程，Agent 通过 MCP 协议调用它
"""
import os
import re
import subprocess
from mcp.server.fastmcp import FastMCP
from skill_manager import list_skills as _list_skills, get_skill as _get_skill

mcp = FastMCP("dev-tools-server")


@mcp.tool()
async def list_dir(path: str) -> str:
    """列出指定目录下的所有文件和文件夹"""
    try:
        items = os.listdir(path)
        return "\n".join(sorted(items))
    except Exception as e:
        return str(e)


@mcp.tool()
async def read_file(path: str) -> str:
    """读取指定文件的内容"""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return str(e)


@mcp.tool()
async def write_file(path: str, content: str) -> str:
    """写内容到指定文件（覆盖写入）"""
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return "写入成功"
    except Exception as e:
        return str(e)


@mcp.tool()
async def edit_file(path: str, old_string: str, new_string: str) -> str:
    """精确替换文件中的指定字符串。找到 old_string 并替换为 new_string。
    如果 old_string 在文件中出现多次，会报错并列出所有位置，请用更多上下文使其唯一。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        count = content.count(old_string)
        if count == 0:
            return f"错误: 未找到指定文本。请用 read_file 确认文件当前内容。"

        if count > 1:
            lines = []
            for i, line in enumerate(content.split("\n"), 1):
                if old_string in line:
                    lines.append(f"  L{i}: {line.strip()[:120]}")
            return f"错误: 匹配到 {count} 处，请提供更多上下文使其唯一：\n" + "\n".join(lines[:10])

        content = content.replace(old_string, new_string, 1)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return "编辑成功"
    except Exception as e:
        return str(e)


@mcp.tool()
async def grep(pattern: str, directory: str, file_pattern: str = "*") -> str:
    """在目录中搜索匹配模式的行。file_pattern 如 '*.py' 过滤文件类型"""
    import fnmatch
    results = []
    try:
        for root, dirs, files in os.walk(directory):
            # 跳过隐藏目录和常见非代码目录
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in
                       ("node_modules", "__pycache__", "venv", ".git")]
            for fname in files:
                if fnmatch.fnmatch(fname, file_pattern):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            for lineno, line in enumerate(f, 1):
                                if re.search(pattern, line, re.IGNORECASE):
                                    results.append(f"{fpath}:{lineno}: {line.rstrip()[:200]}")
                    except Exception:
                        pass
        if not results:
            return f"未找到匹配 '{pattern}' 的行"
        return "\n".join(results[:50])  # 最多 50 条
    except Exception as e:
        return str(e)


@mcp.tool()
async def glob(pattern: str, directory: str = ".") -> str:
    """按文件模式搜索文件。例如 '**/*.py'、'*.tsx'、'src/**/*.js'"""
    from pathlib import Path
    try:
        base = Path(directory)
        matches = sorted(base.glob(pattern))
        results = []
        for p in matches:
            if p.is_file():
                parts = p.relative_to(base).parts
                if any(part.startswith(".") for part in parts):
                    continue
                if any(part in ("node_modules", "__pycache__", "venv") for part in parts):
                    continue
                results.append(str(p))
        if not results:
            return f"未找到匹配 '{pattern}' 的文件"
        return "\n".join(results[:50])
    except Exception as e:
        return str(e)


@mcp.tool()
async def run_command(command: str, cwd: str = ".") -> str:
    """执行 shell 命令并返回输出。用于跑测试、lint、git 等"""
    try:
        result = subprocess.run(
            command, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        output = result.stdout
        if result.stderr:
            output += "\n[stderr]\n" + result.stderr
        if not output.strip():
            output = f"(退出码: {result.returncode})"
        return output[:3000]  # 截断过长输出
    except subprocess.TimeoutExpired:
        return "命令超时（60 秒）"
    except Exception as e:
        return str(e)


@mcp.tool()
async def list_skills() -> str:
    """列出所有可用的 Skill 模板。返回 name、description、触发词。
    当你遇到不熟悉的流程或用户要求做某类任务时，先调用它看看有没有现成的操作模板。"""
    import json
    skills = _list_skills()
    if not skills:
        return "(没有安装任何 Skill)"
    return json.dumps(skills, ensure_ascii=False, indent=2)


@mcp.tool()
async def get_skill(name: str) -> str:
    """获取指定 Skill 的完整操作步骤。name 参数可以是 skill 名称或文件名。
    调用 list_skills 查看有哪些可用 Skill，然后传入它的 name 字段。"""
    content = _get_skill(name)
    if content is None:
        available = [s["name"] for s in _list_skills()]
        return f"未找到 '{name}'。可用的 skill: {', '.join(available)}"
    return content


if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_stdio_async())
