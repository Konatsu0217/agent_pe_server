# PE Server - Prompt Engine 服务

一个**高性能** （*AI说的，我不承认性能高*）的提示词引擎服务，用于构建LLM请求，支持工具调用、RAG检索和会话历史管理。

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

**接口描述**：根据用户查询构建完整的LLM请求，包含系统提示词、工具、RAG结果和会话历史。

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
                "role": "system", 
                "content": "RAG检索结果..."
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
  - `messages` (array): 消息列表，包含系统提示词、RAG结果、历史对话和当前查询
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
                "role": "system",
                "content": "RAG Retrieved Knowledge Chunks:\n1. (score=0.95) source=ml_docs -- 机器学习是人工智能的一个分支..."
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
        "enable_rag": true,               // 是否启用RAG检索
        "max_token_budget": 7000,         // token预算上限
        "system_prompt_path": "systemPrompt.json",  // 系统提示词文件路径
        "tool_service_url": "http://localhost:8000/tool/get_tool_list",     // 工具服务地址
        "rag_service_url": "http://localhost:8000/rag/query_and_embedding", // RAG服务地址
        "session_history_service_url": "http://localhost:8000/session/history", // 会话历史服务地址
        "rag_top_k": 8,                   // RAG检索结果数量
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
2. **RAG服务** (`rag_service_url`)：提供知识检索功能
3. **会话历史服务** (`session_history_service_url`)：提供历史对话记录


## 📝 注意事项

1. 确保所有依赖的外部服务正常运行
2. 根据实际需求调整token预算和历史轮数
3. 监控外部服务的响应时间和可用性
4. 定期检查和更新系统提示词内容
