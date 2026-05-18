# AI Agent Development Framework

从零构建的 AI Agent 开发框架，覆盖 **ReAct Agent、MCP 工具协议、Multi-Agent 编排、RAG 知识库、记忆管理、Deep Research** 六大模块。

## 快速开始

```bash
# 1. 安装依赖
pip install openai chromadb sentence-transformers httpx python-dotenv mcp

# 2. 配置 API Key（从 DeepSeek 获取: https://platform.deepseek.com）
cp .env.example .env
# 编辑 .env，填入你的 DEEPSEEK_API_KEY


```

## 模块概览

| 模块 | 入口文件 | 能力 |
|------|---------|------|
| **ReAct 核心** | `hello_agent.py` | 最精简的 ReAct 循环，展示 Agent = LLM + 工具 + 循环的本质 |
| **MCP Server** | `mcp_server.py` | 7 个标准工具（文件读写/搜索/Shell/技能管理），stdio/JSON-RPC 通信 |
| **AI Dev Agent** | `ai_dev_agent.py` | 综合开发 Agent，整合 MCP + Memory + Skill，自主探索→修改→验证→提交 |
| **Multi-Agent** | `multi_agent.py` | Manager + Sub-Agent 委派架构，子 Agent 独立 ReAct 循环 |
| **记忆管理** | `memory_manager.py` | 滑动窗口 + LLM 摘要混合压缩，分层再压缩，极端场景重要性截断 |
| **RAG 知识库** | `unified_rag.py` | ChromaDB + sentence-transformers，代码按函数边界切、文档按标题段落切 |
| **Deep Research** | `deep_research.py` | 拆解问题 → Bing+本地双源搜索 → 充分度评估 → 自动追问 → 综合报告 |
| **Skill 管理** | `skill_manager.py` | Skill 模板发现/解析/匹配，框架层注入，模型无感 |

## 核心设计

### MemoryManager — 混合压缩策略

```
对话超 token 阈值 → 从尾往前找切分点 → LLM 压缩旧消息为摘要
→ 检测已有摘要层级，递增再压缩（L1→L2→L3） → 仍超限则重要性截断
```

- Token 级阈值（非消息条数），中英文混合估算
- 分层再压缩（摘要的摘要），防止长对话信息熵减
- 极端场景 6 级优先级截断兜底

### MCP Server — 工具动态发现

工具设计对标 Claude Code，`list_dir / read_file / write_file / edit_file / grep / glob / run_command`，新增工具只改 Server，Agent 代码不动。

### Multi-Agent — 委派架构

Manager 负责任务拆解、分配与结果汇总，每个 Sub-Agent 拥有独立 ReAct 循环和限定工具集，支持并行执行。

### RAG — 三层解耦

```
切块层（CodeChunker + DocumentChunker）→ 索引检索层（ChromaDB + embedding）→ 服务化 MCP 层
```

- CodeChunker：按 `def` / `class` 边界切分，保护代码结构
- DocumentChunker：标题 → 段落两级切分
- 支持按 `code` / `document` / `all` 过滤检索

### Deep Research — 五步闭环

```
LLM 拆解问题 → Bing + 本地知识库双源搜索 → 信息充分度评估 → 自动追问深挖（最多 2 轮） → 结构化综合报告
```

双源搜索可插拔：每个搜索源实现 `search(query) → list[dict]` 即可接入。

## 项目结构

```
agent_learning/
├── hello_agent.py          # 入门：最简 ReAct Agent
├── ai_dev_agent.py         # 综合：AI 开发工程师 Agent
├── mcp_server.py           # MCP Server（7 个工具）
├── memory_manager.py       # 记忆管理模块
├── multi_agent.py          # Multi-Agent 编排
├── deep_research.py        # Deep Research Agent
├── unified_rag.py          # 统一 RAG 系统
├── chunkers.py             # 代码/文档切块器
├── skill_manager.py        # Skill 管理器
├── agent_with_mcp.py       # ReAct + MCP 示例
├── agent_with_rag.py       # ReAct + RAG 示例
├── rag_demo.py             # RAG 独立演示
├── rag_mcp_server.py       # RAG MCP Server
├── long_text_pipeline.py   # 长文本处理管线
├── skills/                 # Skill 模板目录
├── docs/                   # 设计文档
├── test_*.py               # 测试文件
├── .env.example            # 环境变量示例
└── .gitignore
```

## API Key 安全

- API Key 存放在 `.env` 文件中，通过 `python-dotenv` 加载
- `.env` 已加入 `.gitignore`，不会被提交到 Git
- 请勿在任何源代码中硬编码 API Key

## License

MIT
