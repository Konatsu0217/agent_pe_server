import time
from typing import List, Optional, Dict, Any
import asyncio
import os
import json
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
import httpx

from util import load_system_prompt, discover_tools, call_rag, rag_chunks_to_system_prompt, get_history_for_session, \
    estimate_tokens_from_messages, compress_assistant_messages, monitor_task, monitor_thread_task, \
    fetch_session_history, BuildRequest, BuildResponse
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
                'pe_system_prompt_path': "systemPrompt.txt",
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


# ======= API Endpoint: 提交并生成 LLM 请求体 =======
@app.post("/pe/build_request", response_model=BuildResponse)
async def build_request(req: BuildRequest):
    """HTTP接口：构建LLM请求"""
    return await build_request_handler(req)


async def build_request_handler(req: BuildRequest) -> BuildResponse:
    """提取出来的build_request处理逻辑，供WebSocket和HTTP共用"""
    session_id = req.session_id
    user_query = req.user_query
    system_resources = req.system_resources
    start_time = time.time()

    try:
        # 并行获取 system prompt、tools、rag（使用连接池和超时控制）
        tasks = []

        # system prompt加载（线程池任务）
        tasks.append(asyncio.to_thread(load_system_prompt, config['pe_system_prompt_path'], session_id))
        tasks.append(call_rag(httpx_client, user_query, config['pe_rag_top_k']))
        tasks.append(fetch_session_history(httpx_client, session_id, config['pe_history_max_rounds']))

        # 设置超时控制
        timeout_seconds = config.get('pe_external_service_timeout', 2)
        system_prompt, rag_results, external_history = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout_seconds
        )

        # 处理异常结果
        if isinstance(system_prompt, Exception):
            print(f"System prompt loading failed: {system_prompt}")
            system_prompt = None
        if isinstance(rag_results, Exception):
            print(f"RAG call failed: {rag_results}")
            rag_results = []
        if isinstance(external_history, Exception):
            print(f"Session history fetch failed: {external_history}")
            external_history = None

    except asyncio.TimeoutError:
        print(f"External services timeout after {timeout_seconds}s")
        system_prompt = None
        rag_results = []
        external_history = None
    except Exception as e:
        print(f"Error in external service calls: {e}")
        system_prompt = None
        rag_results = []
        external_history = None

    # messages 顺序：system, rag(system), history..., user
    messages: List[Dict[str, str]] = []
    if system_prompt:
        mes = {"role": "system", "content": system_prompt}
        if system_resources is not "":
            mes["content"] += f"\n {system_resources}"
        messages.append(mes)

    if rag_results:
        messages.append(rag_results)

    # 当前query
    if user_query:
        messages.append({"role": "user", "content": user_query})

    if external_history:
        messages.append({"role": "system", "content": external_history})

    # 估算 token
    estimated_tokens = estimate_tokens_from_messages(messages)

    # 构建最终 LLM 请求体（符合 OpenAI Chat style）
    llm_request = {
        # 模型在 Agent-Core中配置
        "messages": messages,
    }

    processing_time = (time.time() - start_time) * 1000
    print(f"Request processed in {processing_time:.2f}ms")

    print(f"LLM Request: {llm_request}")

    return BuildResponse(
        llm_request=llm_request,
        estimated_tokens=estimated_tokens,
    )


# ======= API: 简单的会话历史管理（仅示例） =======
class AppendMessageReq(BaseModel):
    session_id: str
    role: str
    content: str


# ======= WebSocket 端点 =======
@app.websocket("/ws/build_prompt")
async def websocket_build_prompt(websocket: WebSocket):
    """
    WebSocket端点：实时处理build_prompt请求
    
    消息格式：
    {
        "type": "build_prompt",
        "request_id": "unique_request_id",
        "data": {
            "session_id": "unique_session_id",
            "system_resources": "系统中的可变资源",
            "user_query": "用户查询内容",
            "stream": false
        }
    }
    
    响应格式：
    {
        "type": "build_prompt_response",
        "request_id": "unique_request_id",
        "status": "success|error",
        "data": { ... },
        "error": "错误信息（如果有）"
    }
    """
    await websocket.accept()
    print(f"WebSocket连接已建立: {websocket.client}")

    try:
        while True:
            # 接收消息
            message_text = await websocket.receive_text()
            print(f"收到WebSocket消息: {message_text}")

            try:
                message = json.loads(message_text)
                message_type = message.get("type")
                request_id = message.get("request_id", f"req_{int(time.time() * 1000)}")

                if message_type == "build_prompt":
                    # 处理build_prompt请求
                    await _handle_build_prompt_websocket(websocket, message.get("data", {}), request_id)

                elif message_type == "ping":
                    # 处理ping请求
                    pong_response = {
                        "type": "pong",
                        "request_id": request_id,
                        "status": "success",
                        "data": {"timestamp": time.time()}
                    }
                    await websocket.send_text(json.dumps(pong_response))

                else:
                    # 未知消息类型
                    error_response = {
                        "type": "error",
                        "request_id": request_id,
                        "status": "error",
                        "error": f"不支持的消息类型: {message_type}"
                    }
                    await websocket.send_text(json.dumps(error_response))

            except json.JSONDecodeError as e:
                error_response = {
                    "type": "error",
                    "status": "error",
                    "error": f"JSON解析错误: {e}"
                }
                await websocket.send_text(json.dumps(error_response))

            except Exception as e:
                error_response = {
                    "type": "error",
                    "status": "error",
                    "error": f"处理消息时出错: {e}"
                }
                await websocket.send_text(json.dumps(error_response))

    except WebSocketDisconnect:
        print(f"WebSocket客户端断开连接: {websocket.client}")
    except Exception as e:
        print(f"WebSocket连接异常: {e}")


async def _handle_build_prompt_websocket(websocket: WebSocket, data: dict, request_id: str):
    """处理WebSocket的build_prompt请求"""
    start_time = time.time()

    try:
        # 提取参数
        session_id = data.get("session_id")
        user_query = data.get("user_query", "")
        system_resources = data.get("system_resources", "")
        stream = data.get("stream", False)

        if not user_query:
            raise ValueError("user_query不能为空")

        print(f"WebSocket处理build_prompt请求 - 会话: {session_id}, 查询: {user_query}")

        # 复用现有的build_request逻辑
        build_request = BuildRequest(session_id=session_id, user_query=user_query, system_resources=system_resources)
        result = await build_request_handler(build_request)

        # 构建WebSocket响应
        processing_time_ms = (time.time() - start_time) * 1000

        response = {
            "type": "build_prompt_response",
            "request_id": request_id,
            "status": "success",
            "data": {
                "llm_request": result.llm_request,
                "estimated_tokens": result.estimated_tokens,
                "processing_time_ms": processing_time_ms
            }
        }

        await websocket.send_text(json.dumps(response))
        print(f"WebSocket响应发送成功 - 请求ID: {request_id}, 处理时间: {processing_time_ms:.2f}ms")

    except Exception as e:
        error_response = {
            "type": "build_prompt_response",
            "request_id": request_id,
            "status": "error",
            "error": f"处理build_prompt请求失败: {e}"
        }
        await websocket.send_text(json.dumps(error_response))
        print(f"WebSocket处理失败 - 请求ID: {request_id}, 错误: {e}")


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
