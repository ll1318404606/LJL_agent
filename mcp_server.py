"""
MCP Server — 文件系统 + 代码搜索 + 命令执行
独立进程，Agent 通过 MCP 协议调用它
"""
import os
import re
import subprocess
from mcp.server.fastmcp import FastMCP

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


if __name__ == "__main__":
    import asyncio
    asyncio.run(mcp.run_stdio_async())
