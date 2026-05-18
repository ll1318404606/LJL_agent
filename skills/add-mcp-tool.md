---
name: add-mcp-tool
description: 给 MCP Server 添加新工具的标准流程。在 mcp_server.py 中加 @mcp.tool() 函数并重启。
triggers:
  - 新工具
  - 添加工具
  - 加个功能
  - 加功能
  - 新增
  - 扩展工具
---

# 给 MCP Server 添加工具

## 前置检查
1. 用 read_file 读取 `D:\agent_learning\mcp_server.py`，确认当前结构
2. 确认新工具的函数名不与已有工具冲突（已有工具通过 MCP 的 list_tools 可见）

## 执行步骤
1. 在 mcp_server.py 中添加新的 `@mcp.tool()` 函数，跟在最后一个工具函数之后
2. 函数签名：`async def tool_name(param: type) -> str:`，必须返回 str
3. docstring 要写清楚工具用途和参数含义（Agent 通过 description 决策是否调用）
4. 用 write_file 写回 mcp_server.py（需要传完整文件内容）
5. Agent 下次连接 MCP Server 时会自动发现新工具（无需手动重启）

## 验证
- 工具添加后，Agent 在下一次对话中就能通过 tool description 看到它
- 用 run_command 测试：`D:\Python\python.exe -m py_compile D:\agent_learning\mcp_server.py`

## 注意
- 新工具的 docstring 是 Agent 判断"何时调用"的唯一依据，写清楚触发场景
- 返回值必须是 str 类型（MCP 协议要求）
- 不要修改已有的工具函数
