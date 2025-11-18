import time
from typing import List, Optional, Dict, Any
import asyncio
import os
import json
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field
import httpx

from util import load_system_prompt, discover_tools, call_rag, rag_chunks_to_system_prompt, get_history_for_session, \
    estimate_tokens_from_messages, compress_assistant_messages, monitor_task, monitor_thread_task, fetch_session_history
from config_manager import ConfigManager


# 配置加载器（从server.py复制过来）
class ConfigLoader:
    _instance = None
    _config = None

    @classmethod
    def get_config(cls, config_path='config.json'):
        if cls._config is None:
            cls._load_config(config_path)
        return cls._config

    @classmethod
    def _load_config(cls, config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # 扁平化配置，便于访问
            cls._config = {
                # 服务器配置
                'port': config_data['server']['port'],
                'workers': config_data['server']['workers'],
                'limit_concurrency': config_data['server']['limit_concurrency'],
                'backlog': config_data['server']['backlog'],
                'reload': config_data['server']['reload'],
                'timeout_keep_alive': config_data['server'].get('timeout_keep_alive', 5),
                # PE Settings
                'pe_enable_history': config_data['pe_settings']['enable_history'],
                'pe_history_max_rounds': config_data['pe_settings']['history_max_rounds'],
                'pe_enable_tools': config_data['pe_settings']['enable_tools'],
                'pe_enable_rag': config_data['pe_settings']['enable_rag'],
                'pe_max_token_budget': config_data['pe_settings']['max_token_budget'],
                'pe_system_prompt_path': config_data['pe_settings']['system_prompt_path'],
                'pe_tool_service_url': config_data['pe_settings']['tool_service_url'],
                'pe_rag_service_url': config_data['pe_settings']['rag_service_url'],
                'pe_rag_top_k': config_data['pe_settings']['rag_top_k'],
                'pe_api_url': config_data['pe_settings']['api_url'],
                'pe_external_service_timeout': config_data['pe_settings'].get('external_service_timeout', 2),
                # 连接池配置
                'connection_pool_size': config_data.get('connection_pool', {}).get('connection_pool_size', 20),
                'connection_timeout': config_data.get('connection_pool', {}).get('connection_timeout', 2),
                'read_timeout': config_data.get('connection_pool', {}).get('read_timeout', 3),
            }
            print(f"配置加载成功: {cls._config}")
        except Exception as e:
            print(f"配置文件加载失败: {str(e)}")
            # 使用默认配置作为后备
            cls._config = {
                'port': 18080,
                'workers': 1,
                'limit_concurrency': 100,
                'backlog': 512,
                'reload': True,
                'timeout_keep_alive': 5,
                # PE Settings 默认值
                'pe_enable_history': True,
                'pe_history_max_rounds': 6,
                'pe_enable_tools': True,
                'pe_enable_rag': True,
                'pe_max_token_budget': 7000,
                'pe_system_prompt_path': "systemPrompt.json",
                'pe_api_url': "/api/build_prompt",
                'pe_tool_service_url': "http://localhost:8000/tool/get_tool_list",
                'pe_rag_service_url': "http://localhost:8000/rag/query_and_embedding",
                'pe_rag_top_k': 3,
                'pe_external_service_timeout': 2,
                # 连接池配置
                'connection_pool_size': 20,
                'connection_timeout': 2,
                'read_timeout': 3,
            }
            print(f"使用默认配置: {cls._config}")

app = FastAPI(title="Prompt Engine (PE) - FastAPI")
# 获取配置
config = ConfigManager.get_config()

# 创建HTTP客户端连接池
httpx_client = httpx.AsyncClient(
    limits=httpx.Limits(
        max_connections=config.get('connection_pool_size', 20),
        max_keepalive_connections=config.get('connection_pool_size', 20),
        keepalive_expiry=30
    ),
    timeout=httpx.Timeout(
        connect=config.get('connection_timeout', 2),
        read=config.get('read_timeout', 3),
        write=config.get('read_timeout', 3),
        pool=config.get('connection_timeout', 2)
    )
)

# ======= 请求 / 响应 模型 ========
class BuildRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="会话ID，用于从缓存中获取历史")
    user_query: str = Field(..., description="用户当前 query")


class BuildResponse(BaseModel):
    llm_request: Dict[str, Any]
    estimated_tokens: int
    trimmed_history_rounds: int


# ======= API Endpoint: 提交并生成 LLM 请求体 =======
@app.post("/pe/build_request", response_model=BuildResponse)
async def build_request(req: BuildRequest):
    session_id = req.session_id
    user_query = req.user_query
    start_time = time.time()

    try:
        # 并行获取 system prompt、tools、rag（使用连接池和超时控制）
        tasks = []
        
        # system prompt加载（线程池任务）
        tasks.append(asyncio.to_thread(load_system_prompt, config['pe_system_prompt_path']))
        
        # tools发现（条件启用）
        if config['pe_enable_tools']:
            tasks.append(discover_tools(httpx_client))
        else:
            tasks.append(asyncio.create_task(asyncio.sleep(0)))  # 空任务
        
        # rag调用（条件启用）
        if config['pe_enable_rag']:
            tasks.append(call_rag(httpx_client, user_query, config['pe_rag_top_k']))
        else:
            tasks.append(asyncio.create_task(asyncio.sleep(0)))  # 空任务
        
        # 会话历史获取（条件启用）
        if config['pe_enable_history']:
            tasks.append(fetch_session_history(httpx_client, session_id))
        else:
            tasks.append(asyncio.create_task(asyncio.sleep(0)))  # 空任务
        
        # 设置超时控制
        timeout_seconds = config.get('pe_external_service_timeout', 2)
        system_prompt, tools_list, rag_results, external_history = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout_seconds
        )
        
        # 处理异常结果
        if isinstance(system_prompt, Exception):
            print(f"System prompt loading failed: {system_prompt}")
            system_prompt = None
        if isinstance(tools_list, Exception):
            print(f"Tools discovery failed: {tools_list}")
            tools_list = []
        if isinstance(rag_results, Exception):
            print(f"RAG call failed: {rag_results}")
            rag_results = []
        if isinstance(external_history, Exception):
            print(f"Session history fetch failed: {external_history}")
            external_history = None
            
    except asyncio.TimeoutError:
        print(f"External services timeout after {timeout_seconds}s")
        system_prompt = None
        tools_list = []
        rag_results = []
        external_history = None
    except Exception as e:
        print(f"Error in external service calls: {e}")
        system_prompt = None
        tools_list = []
        rag_results = []
        external_history = None

    # messages 顺序：system, rag(system), history..., user
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    rag_system_msg = rag_chunks_to_system_prompt(rag_results)
    if rag_system_msg:
        messages.append(rag_system_msg)

    # attach history (受 setting 控制)
    trimmed_history_rounds = config['pe_history_max_rounds']
    # 优先使用从外部服务获取的历史记录，如果没有则使用本地内存历史
    if external_history:
        history_messages = external_history[-trimmed_history_rounds*2:]  # 每条对话包含user和assistant两条消息
    else:
        history_messages = get_history_for_session(session_id, trimmed_history_rounds)
    messages.extend(history_messages)

    # 最后加入当前 user query
    messages.append({"role": "user", "content": user_query})

    # 估算 token
    estimated_tokens = estimate_tokens_from_messages(messages)

    # 剪裁历史直到满足预算
    trimmed_rounds = trimmed_history_rounds
    while estimated_tokens > config['pe_max_token_budget'] and trimmed_rounds > 0:
        trimmed_rounds -= 1
        # 优先使用外部历史记录进行裁剪
        if external_history:
            history_messages = external_history[-trimmed_rounds*2:]
        else:
            history_messages = get_history_for_session(session_id, trimmed_rounds)
        # 可选：对 assistant 消息进行压缩
        history_messages = compress_assistant_messages(history_messages, target_chars=600)
        # rebuild messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if rag_system_msg:
            messages.append(rag_system_msg)
        messages.extend(history_messages)
        messages.append({"role": "user", "content": user_query})
        estimated_tokens = estimate_tokens_from_messages(messages)

    # 构建最终 LLM 请求体（符合 OpenAI Chat style）
    llm_request = {
        # 模型在 Agent-Core中配置
        "messages": messages,
        "tools": tools_list if config['pe_enable_tools'] else [],
        "max_tokens": config['pe_max_token_budget'],
    }

    processing_time = (time.time() - start_time) * 1000
    print(f"Request processed in {processing_time:.2f}ms")

    return BuildResponse(
        llm_request=llm_request,
        estimated_tokens=estimated_tokens,
        trimmed_history_rounds=trimmed_rounds,
    )


# ======= API: 简单的会话历史管理（仅示例） =======
class AppendMessageReq(BaseModel):
    session_id: str
    role: str
    content: str


# ======= 启动（用于直接运行） =======
if __name__ == "__main__":
    import uvicorn

    # 使用配置文件中的设置启动服务
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=config['port'], 
        workers=config.get('workers', 1),
        limit_concurrency=config.get('limit_concurrency', 100),
        backlog=config.get('backlog', 512),
        reload=config.get('reload', True),
        timeout_keep_alive=config.get('timeout_keep_alive', 5),
    )
