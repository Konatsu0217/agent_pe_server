# PE Server - Prompt Engine 服务

图一乐的提示词引擎

## 重要变更
- 自本版本起，PE 不再调用或依赖 RAG；RAG 将在主调度器中实现与统一管理。本文档中关于 RAG 的字段与示例仅作历史参考，PE 层不会产生或拼装 RAG 系统消息。

## Todo
- [ ] context太大的历史会话丢弃逻辑

- [ ] 历史会话压缩方法

上面两个不确定是否要放到pe里

- [ ] 几个part放的位置确认下


## 🚀 快速开始

### 安装依赖
```bash
pip install -r requirements.txt
```

### 启动服务
```bash
python main.py
```

服务默认运行在 `http://127.0.0.1:25535`

## 📋 API接口文档

### 1. 构建LLM请求 - `/pe/build_request`

**接口描述**：根据用户查询构建完整的LLM请求，包含系统提示词、会话历史和用户查询。

#### 请求结构
```json
{
    "session_id": "optional_session_id",  // 必填，会话ID用于历史记录
    "user_query": "用户输入的查询内容"      // 必填，用户当前查询
}
```

**字段说明**：
- `session_id` (string, optional): 会话ID，用于获取历史对话记录
- `user_query` (string, required): 用户的查询内容

#### 响应结构
```json
{
    "llm_request": {
        "messages": [
            {
                "role": "system",
                "content": "系统提示词内容..."
            },
            {
                "role": "user",
                "content": "用户查询"
            },
            {
                "role": "assistant", 
                "content": "助手回复"
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "tool_name",
                    "description": "工具描述",
                    "parameters": {
                        "type": "object",
                        "properties": {...}
                    }
                }
            }
        ],
        "max_tokens": 7000
    },
    "estimated_tokens": 3469,      // 估算的token数量
    "trimmed_history_rounds": 6    // 保留的历史对话轮数
}
```

**字段说明**：
- `llm_request` (object): 符合OpenAI API格式的LLM请求体
  - `messages` (array): 消息列表，包含系统提示词、历史对话和当前查询（不再包含 RAG 结果）
  - `tools` (array): 可用工具列表，符合OpenAI工具调用格式
  - `max_tokens` (integer): 最大token限制
- `estimated_tokens` (integer): 估算的总token数量
- `trimmed_history_rounds` (integer): 实际保留的历史对话轮数（可能因token限制被裁剪）

#### 使用示例

**请求示例**：
```bash
curl -X POST "http://127.0.0.1:25535/pe/build_request" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "user_123",
    "user_query": "什么是机器学习？"
  }'
```

**响应示例**：
```json
{
    "llm_request": {
        "messages": [
            {
                "role": "system",
                "content": "你是一个专业的AI助手，帮助用户解答各种问题。"
            },
            {
                "role": "user",
                "content": "什么是机器学习？"
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge",
                    "description": "搜索知识库",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"}
                        }
                    }
                }
            }
        ],
        "max_tokens": 7000
    },
    "estimated_tokens": 156,
    "trimmed_history_rounds": 0
}
```

### 2. 健康检查 - `/docs`

**接口描述**：FastAPI自动生成的API文档页面

**请求方式**：GET

**响应**：返回Swagger UI文档页面

### 3. WebSocket接口 - `/ws/build_prompt`

**接口描述**：WebSocket长连接接口，用于实时处理build_prompt请求，支持双向通信和更低的延迟。

#### 连接建立
```javascript
const ws = new WebSocket('ws://127.0.0.1:25535/ws/build_prompt');
```

#### 消息格式

**请求消息**：
```json
{
    "type": "build_prompt",
    "request_id": "unique_request_id_123",
    "data": {
        "session_id": "optional_session_id",
        "user_query": "用户查询内容",
        "stream": false
    }
}
```

**响应消息**：
```json
{
    "type": "build_prompt_response",
    "request_id": "unique_request_id_123",
    "status": "success",
    "data": {
        "llm_request": {
            "messages": [...],
            "tools": [...],
            "max_tokens": 7000
        },
        "estimated_tokens": 156,
        "trimmed_history_rounds": 0,
        "processing_time_ms": 45.23
    }
}
```

**错误响应**：
```json
{
    "type": "build_prompt_response",
    "request_id": "unique_request_id_123",
    "status": "error",
    "error": "处理请求失败的具体原因"
}
```

**心跳检测（Ping）**：
```json
{
    "type": "ping",
    "request_id": "ping_123"
}
```

**心跳响应（Pong）**：
```json
{
    "type": "pong",
    "request_id": "ping_123",
    "status": "success",
    "data": {"timestamp": 1700000000.123}
}
```

#### WebSocket使用示例

**JavaScript客户端**：
```javascript
// 建立连接
const ws = new WebSocket('ws://127.0.0.1:25535/ws/build_prompt');

ws.onopen = function(event) {
    console.log('WebSocket连接已建立');
    
    // 发送build_prompt请求
    const request = {
        type: "build_prompt",
        request_id: "req_" + Date.now(),
        data: {
            session_id: "user_123",
            user_query: "什么是机器学习？",
            stream: false
        }
    };
    
    ws.send(JSON.stringify(request));
};

ws.onmessage = function(event) {
    const response = JSON.parse(event.data);
    console.log('收到响应:', response);
    
    if (response.type === 'build_prompt_response') {
        if (response.status === 'success') {
            console.log('LLM请求构建成功:', response.data);
        } else {
            console.error('请求处理失败:', response.error);
        }
    }
};

ws.onerror = function(error) {
    console.error('WebSocket错误:', error);
};

ws.onclose = function(event) {
    console.log('WebSocket连接已关闭');
};
```

**Python客户端**：
```python
import asyncio
import json
import websockets

async def test_websocket():
    uri = "ws://127.0.0.1:25535/ws/build_prompt"
    
    async with websockets.connect(uri) as websocket:
        # 发送请求
        request = {
            "type": "build_prompt",
            "request_id": "req_001",
            "data": {
                "user_query": "帮我写一段Python代码",
                "session_id": "test_session"
            }
        }
        
        await websocket.send(json.dumps(request))
        
        # 接收响应
        response = await websocket.recv()
        result = json.loads(response)
        print("响应:", result)

asyncio.run(test_websocket())
```

#### WebSocket优势
- **低延迟**：长连接避免了HTTP连接建立的开销
- **双向通信**：支持服务器主动向客户端推送消息
- **实时性**：适合需要快速响应的交互式应用
- **心跳检测**：内置ping/pong机制保持连接活跃
- **请求追踪**：通过request_id匹配请求和响应

#### WebSocket vs HTTP
| 特性 | WebSocket | HTTP |
|------|-----------|------|
| 连接方式 | 长连接 | 短连接 |
| 延迟 | 低 | 相对较高 |
| 双向通信 | 支持 | 不支持 |
| 适用场景 | 实时交互、频繁请求 | 偶尔请求、简单查询 |
| 复杂度 | 较高 | 简单 |

#### 注意事项
1. WebSocket连接需要保持活跃，建议实现心跳机制
2. 处理好连接断开和重连逻辑
3. 对于大量并发连接，需要考虑连接池管理
4. 生产环境建议使用wss://协议进行加密

## ⚙️ 配置说明

### 配置文件结构（config.json）

```json
{
    "server": {
        "port": 25535,                    // 服务端口
        "workers": 1,                     // 工作进程数
        "limit_concurrency": 50,          // 并发限制
        "backlog": 1024,                  // 连接队列长度
        "reload": false,                  // 是否自动重载
        "timeout_keep_alive": 5           // keepalive超时时间
    },
    "pe_settings": {
        "api_url": "/pe/build_request",   // API路径
        "enable_history": false,          // 是否启用历史记录
        "history_max_rounds": 6,          // 最大历史轮数
        "enable_tools": true,             // 是否启用工具调用
        "enable_rag": true,               // （已废弃）是否启用RAG检索
        "max_token_budget": 7000,         // token预算上限
        "system_prompt_path": "systemPrompt.txt",  // 系统提示词文件路径
        "tool_service_url": "http://localhost:8000/tool/get_tool_list",     // 工具服务地址
        "rag_service_url": "http://localhost:8000/rag/query_and_embedding", // （已废弃）RAG服务地址
        "session_history_service_url": "http://localhost:8000/session/history", // 会话历史服务地址
        "rag_top_k": 8,                   // （已废弃）RAG检索结果数量
        "external_service_timeout": 2     // 外部服务超时时间（秒）
    },
    "connection_pool": {
        "connection_pool_size": 20,       // 连接池大小
        "connection_timeout": 2,          // 连接超时时间
        "read_timeout": 3                 // 读取超时时间
    }
}
```

## 🔧 依赖服务

PE Server依赖以下外部服务：

1. **工具服务** (`tool_service_url`)：提供可用工具列表
2. **会话历史服务** (`session_history_service_url`)：提供历史对话记录

> 注：RAG 服务由主调度器统一调用与管理，PE 不再直接依赖。


## 📝 注意事项

1. 确保所有依赖的外部服务正常运行
2. 根据实际需求调整token预算和历史轮数
3. 监控外部服务的响应时间和可用性
4. 定期检查和更新系统提示词内容
