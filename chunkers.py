"""
通用切块器 — CodeChunker（按函数/类边界切代码）+ DocumentChunker（按段落/标题切文档）
统一输出格式：{id, content, doc_type, source, path}
"""
import os, re


# ─── 代码切块器 ────────────────────────────────────

class CodeChunker:
    """
    按函数/类定义行切分代码。
    - 优先在 def/class 边界切，保护代码结构
    - 超大函数（>max_lines）再按固定行数子切
    """
    # 匹配顶级定义：def / class / async def
    DEF_PATTERN = re.compile(r'^(def |class |async def )', re.MULTILINE)

    def __init__(self, max_lines: int = 80, min_lines: int = 8):
        self.max_lines = max_lines
        self.min_lines = min_lines

    def chunk_file(self, path: str) -> list[dict]:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if not content.strip():
            return []

        lines = content.split("\n")
        fname = os.path.basename(path)

        # 找所有函数/类定义行号
        boundaries = [0]
        for i, line in enumerate(lines):
            if self.DEF_PATTERN.match(line.strip()):
                boundaries.append(i)
        boundaries.append(len(lines))

        chunks = []
        for j in range(len(boundaries) - 1):
            start = boundaries[j]
            end = boundaries[j + 1]
            chunk_lines = lines[start:end]
            chunk_text = "\n".join(chunk_lines)

            # 跳过纯空白块（边界之间的空行）
            if not chunk_text.strip():
                continue

            # 跳过过小的块：合并到相邻块（这里简化处理，直接保留最小块）
            if len(chunk_lines) < self.min_lines and j > 0:
                continue

            # 确定元素名
            if j == 0 and start == 0:
                element = "__header__"
            else:
                first_line = lines[start].strip()
                m = self.DEF_PATTERN.search(first_line)
                if m:
                    # 提取 "def foo" / "class Bar" / "async def foo"
                    element = first_line.split("(")[0].strip().rstrip(":")
                else:
                    element = f"__block_{j}__"

            # 大函数二次切分
            if len(chunk_lines) > self.max_lines:
                sub = self._sub_split(chunk_lines, element, fname, path, start)
                chunks.extend(sub)
            else:
                chunks.append({
                    "id": f"{fname}__L{start+1}_{element}",
                    "content": chunk_text,
                    "doc_type": "code",
                    "source": fname,
                    "path": path,
                    "element": element,
                    "line_start": start + 1,
                    "line_end": end,
                })

        return chunks

    def _sub_split(self, lines: list[str], element: str,
                   fname: str, path: str, base_line: int) -> list[dict]:
        """超大函数按固定行数子切，重叠保留上下文"""
        overlap = 5
        chunks = []
        pos = 0
        part = 0
        while pos < len(lines):
            seg = lines[pos:pos + self.max_lines]
            seg_text = "\n".join(seg)
            if not seg_text.strip():
                break
            chunks.append({
                "id": f"{fname}__L{base_line+pos+1}_{element}_p{part}",
                "content": seg_text,
                "doc_type": "code",
                "source": fname,
                "path": path,
                "element": f"{element}[part{part}]",
                "line_start": base_line + pos + 1,
                "line_end": base_line + min(pos + self.max_lines, len(lines)),
            })
            pos += self.max_lines - overlap
            part += 1
        return chunks


# ─── 文档切块器 ────────────────────────────────────

class DocumentChunker:
    """
    按标题+段落切分 Markdown/文本文档。
    - 先在 ## / ### 标题处切
    - 每个 section 内再按段落（空行）切
    - 小段落合并到 ~target_size 长度
    """

    HEADING_PATTERN = re.compile(r'^#{1,4}\s+')

    def __init__(self, target_size: int = 500, overlap_lines: int = 2):
        self.target_size = target_size
        self.overlap_lines = overlap_lines

    def chunk_file(self, path: str) -> list[dict]:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if not content.strip():
            return []

        fname = os.path.basename(path)

        # 第一步：按标题切 section
        sections = self._split_by_headings(content)

        chunks = []
        for sec_idx, (section_title, section_text) in enumerate(sections):
            # 第二步：section 内按段落切
            paragraphs = self._split_paragraphs(section_text)
            # 第三步：合并小段落到目标大小
            merged = self._merge_paragraphs(paragraphs)

            for i, para_text in enumerate(merged):
                chunk_id = f"{fname}__s{sec_idx}_{section_title[:30]}_p{i}"
                chunks.append({
                    "id": chunk_id,
                    "content": para_text,
                    "doc_type": "document",
                    "source": fname,
                    "path": path,
                    "section": section_title,
                    "chunk_index": i,
                })

        return chunks

    def _split_by_headings(self, text: str) -> list[tuple[str, str]]:
        """按标题行切分，返回 [(标题, 正文), ...]"""
        lines = text.split("\n")
        sections = []
        current_title = "__opening__"
        current_lines = []

        for line in lines:
            if self.HEADING_PATTERN.match(line.strip()):
                if current_lines:
                    sections.append((current_title, "\n".join(current_lines)))
                current_title = line.strip().lstrip("#").strip()
                current_lines = []
            else:
                current_lines.append(line)

        if current_lines:
            sections.append((current_title, "\n".join(current_lines)))

        return sections

    def _split_paragraphs(self, text: str) -> list[str]:
        """按空行切段落"""
        raw = re.split(r'\n\s*\n', text)
        return [p.strip() for p in raw if p.strip()]

    def _merge_paragraphs(self, paragraphs: list[str]) -> list[str]:
        """合并小段落到接近 target_size"""
        merged = []
        buf = ""
        for p in paragraphs:
            if len(buf) + len(p) < self.target_size:
                buf += ("\n\n" + p) if buf else p
            else:
                if buf:
                    merged.append(buf)
                buf = p
        if buf:
            merged.append(buf)
        return merged


# ─── 统一入口 ────────────────────────────────────

def chunk_file(path: str) -> list[dict]:
    """根据文件类型自动选择切块器"""
    ext = os.path.splitext(path)[1].lower()
    fname = os.path.basename(path)

    if ext in (".py", ".js", ".ts", ".go", ".java", ".rs", ".cpp", ".c"):
        return CodeChunker().chunk_file(path)
    elif ext in (".md", ".txt", ".rst"):
        return DocumentChunker().chunk_file(path)
    else:
        # 未知类型当成文档处理
        return DocumentChunker().chunk_file(path)


def chunk_directory(directory: str) -> tuple[list[dict], dict]:
    """扫描整个目录，返回 (所有chunk, 统计信息)"""
    all_chunks = []
    stats = {"code_files": 0, "code_chunks": 0, "doc_files": 0, "doc_chunks": 0}

    code_exts = {".py", ".js", ".ts", ".go", ".java", ".rs", ".cpp", ".c"}
    doc_exts = {".md", ".txt", ".rst"}

    for root, _, files in os.walk(directory):
        # 跳过隐藏目录
        if os.path.basename(root).startswith("."):
            continue
        for fname in files:
            path = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()

            if ext not in code_exts and ext not in doc_exts:
                continue

            chunks = chunk_file(path)

            if ext in code_exts:
                stats["code_files"] += 1
                stats["code_chunks"] += len(chunks)
            else:
                stats["doc_files"] += 1
                stats["doc_chunks"] += len(chunks)

            all_chunks.extend(chunks)
            print(f"  [{ext}] {fname} → {len(chunks)} 块")

    return all_chunks, stats


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    target = r"D:\agent_learning"
    print(f"扫描目录: {target}\n")
    chunks, stats = chunk_directory(target)
    print(f"\n=== 统计 ===")
    print(f"代码文件: {stats['code_files']} 个, {stats['code_chunks']} 块")
    print(f"文档文件: {stats['doc_files']} 个, {stats['doc_chunks']} 块")
    print(f"总计: {len(chunks)} 块")

    # 打印每个 chunk 的类型标签
    print(f"\n=== 各类型 chunk 示例 ===")
    for t in ["code", "document"]:
        typed = [c for c in chunks if c["doc_type"] == t]
        if typed:
            c = typed[0]
            print(f"\n[{t}] id={c['id']}")
            print(f"    source={c['source']}, element/section={c.get('element') or c.get('section')}")
            print(f"    content preview: {c['content'][:120]}...")
