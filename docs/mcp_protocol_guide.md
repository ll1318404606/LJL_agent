# MCP 协议完整指南

## 什么是 MCP

MCP（Model Context Protocol）是 Anthropic 于 2024 年底发布的一种开放协议，旨在标准化 AI 模型与外部工具、数据源之间的通信方式。它的设计理念类似于 USB-C 接口——提供一个统一的"插口"，让任何 AI 模型都能连接任何工具。

在 MCP 出现之前，每个 AI 应用都需要为不同的工具编写定制化的集成代码。比如连接数据库要写一套代码，连接文件系统要写另一套，连接搜索引擎又要写一套。MCP 解决了这个问题：只需实现一次 MCP 接口，所有兼容 MCP 的 AI 模型都能使用你的工具。

## 核心架构

MCP 采用客户端-服务器架构，包含三个核心角色：

### MCP Host
Host 是承载 AI 模型的应用程序，例如 Claude Desktop、Cursor IDE、或者你自己写的 Python 脚本。Host 负责管理多个 MCP 连接，并将工具列表传递给 AI 模型。

### MCP Client
Client 与 Server 建立一对一的连接。每个 Client 维护一个独立的通信通道（通常是 stdio 或 HTTP），负责发送请求和接收响应。

### MCP Server
Server 是实际的工具提供者。它暴露一组工具（Tools）、资源（Resources）和提示模板（Prompts）。Server 是独立进程，可以用任何语言实现——Python、Node.js、Go、Rust 等。

## 三大核心概念

### 1. Tools（工具）
工具是模型可以调用的函数。每个工具有名称、描述和参数 Schema。模型根据描述决定何时调用工具，根据 Schema 生成调用参数。

```python
@mcp.tool()
def search_database(query: str, limit: int = 10) -> str:
    """搜索数据库，返回匹配的记录"""
    # 实际查询逻辑
    return results
```

关键设计原则：工具描述要精确，让模型能准确判断使用场景。参数类型要明确，便于模型生成正确的调用参数。

### 2. Resources（资源）
资源是模型可以读取的数据。与工具不同，资源是只读的，不执行任何操作。资源用 URI 标识，类似 REST API 的端点。

```python
@mcp.resource("file://{path}")
def read_file(path: str) -> str:
    """读取文件内容"""
    with open(path) as f:
        return f.read()
```

### 3. Prompts（提示模板）
预定义的提示词模板，帮助用户快速开始特定任务。例如代码审查模板、文档生成模板等。

## 传输机制

MCP 支持多种传输方式：

### stdio（标准输入输出）
最常用的本地通信方式。Server 作为子进程启动，通过标准输入输出与 Client 交换 JSON-RPC 消息。优点是零网络配置，适合本地开发。

### HTTP + SSE
适用于远程 Server。Client 通过 HTTP 发送请求，通过 SSE（Server-Sent Events）接收流式响应。适合将工具部署为云服务。

### Streamable HTTP
MCP 2025 版新增的传输方式，统一了 HTTP 和 SSE 到一个端点上，简化了部署。

## JSON-RPC 协议

MCP 使用 JSON-RPC 2.0 作为底层消息格式。每种操作对应一个标准方法：

| 方法 | 方向 | 说明 |
|------|------|------|
| initialize | C→S | 协商协议版本和能力 |
| tools/list | C→S | 获取可用工具列表 |
| tools/call | C→S | 调用指定工具 |
| resources/list | C→S | 获取可用资源列表 |
| resources/read | C→S | 读取资源内容 |
| notifications/initialized | C→S | 初始化完成通知 |

每条消息包含 `jsonrpc`、`method`、`id`、`params` 字段，响应包含 `result` 或 `error`。

## Python 生态

### FastMCP
FastMCP 是 Python 社区最流行的 MCP 框架。它提供了简洁的装饰器语法，支持自动生成 JSON Schema，内置多种传输方式。

```python
from fastmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
def add(a: int, b: int) -> int:
    return a + b

mcp.run()  # 默认 stdio 模式
```

### mcp 官方包
Anthropic 提供的 `mcp` Python 包，包含客户端和服务端的基础类。FastMCP 就是在它的基础上封装的。

## Agent 如何通过 MCP 使用工具

完整的 Agent-MCP 交互流程：

1. **启动阶段**：Agent 启动 MCP Server 作为子进程，建立 stdio 连接
2. **初始化**：交换协议版本，协商支持的能力
3. **发现工具**：调用 `tools/list` 获取所有可用工具，转换为 LLM 需要的 Function Calling 格式
4. **运行循环**：
   - LLM 决定是否调用工具
   - 如果需要，生成工具名称和参数
   - Agent 通过 MCP 调用工具
   - 工具返回结果
   - 结果追加到对话历史
   - LLM 继续思考或给出最终回答

核心价值：**加工具不改 Agent 代码**。新工具只需在 Server 端加一个装饰器函数，Agent 重启后自动发现。

## 设计最佳实践

1. **单一职责**：每个工具只做一件事，描述精确
2. **错误处理**：工具返回有意义的错误信息，方便 LLM 自我纠错
3. **输入验证**：在 Server 端验证参数，防止注入和异常
4. **超时控制**：长时间运行的工具要有超时机制
5. **日志记录**：记录每次工具调用，便于调试和审计
