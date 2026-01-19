import asyncio
import json
import time
from typing import List, Dict, Any
from pathlib import Path

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from config_manager import ConfigManager
from util import estimate_tokens_from_messages, fetch_session_history, BuildRequest, \
    BuildResponse
from template_engine import get_template_engine

app = FastAPI(title="Prompt Engine (PE) - FastAPI")
# 获取配置
config = ConfigManager.get_config()

# 初始化模板引擎
# 模板目录在 code/ 目录的同级目录 templates/
templates_dir = Path(__file__).resolve().parent.parent / "templates"
engine = get_template_engine(str(templates_dir))

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
        # 获取会话历史
        external_history = await fetch_session_history(httpx_client, session_id, config['pe_history_max_rounds'])
    except Exception as e:
        print(f"Session history fetch failed: {e}")
        external_history = None

    # ======= 模版烘焙 (Baking) =======
    # 将系统资源等变量传入模板进行烘焙
    template_context = {
        "session_id": session_id,
        "system_resources": system_resources,
        "user_query": user_query
    }
    
    system_prompt = engine.render(config['pe_system_prompt_path'], template_context)

    # messages 顺序：system, history..., user
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    # 当前query
    if user_query:
        messages.append({"role": "user", "content": user_query})

    if external_history:
        # 如果历史记录是字符串，转为系统消息（兼容旧逻辑）
        if isinstance(external_history, str):
            messages.append({"role": "system", "content": external_history})
        elif isinstance(external_history, list):
            # 如果是列表，直接拼接到messages中（通常历史记录应该在user query之前）
            # 调整顺序：system -> history -> user
            system_msg = messages[0] if messages and messages[0]["role"] == "system" else None
            user_msg = messages[-1] if messages and messages[-1]["role"] == "user" else None
            
            new_messages = []
            if system_msg:
                new_messages.append(system_msg)
            new_messages.extend(external_history)
            if user_msg:
                new_messages.append(user_msg)
            messages = new_messages

    # 估算 token
    estimated_tokens = estimate_tokens_from_messages(messages)

    # 构建最终 LLM 请求体（符合 OpenAI Chat style）
    llm_request = {
        "messages": messages,
    }

    processing_time = (time.time() - start_time) * 1000
    print(f"Request processed in {processing_time:.2f}ms")
    print(f"LLM Request: {llm_request}")

    return BuildResponse(
        llm_request=llm_request,
        estimated_tokens=estimated_tokens,
    )


# ======= WebSocket 端点 =======
@app.websocket("/ws/build_prompt")
async def websocket_build_prompt(websocket: WebSocket):
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
                    await _handle_build_prompt_websocket(websocket, message.get("data", {}), request_id)
                elif message_type == "ping":
                    pong_response = {
                        "type": "pong",
                        "request_id": request_id,
                        "status": "success",
                        "data": {"timestamp": time.time()}
                    }
                    await websocket.send_text(json.dumps(pong_response))
                else:
                    error_response = {
                        "type": "error",
                        "request_id": request_id,
                        "status": "error",
                        "error": f"不支持的消息类型: {message_type}"
                    }
                    await websocket.send_text(json.dumps(error_response))

            except json.JSONDecodeError as e:
                error_response = {"type": "error", "status": "error", "error": f"JSON解析错误: {e}"}
                await websocket.send_text(json.dumps(error_response))
            except Exception as e:
                error_response = {"type": "error", "status": "error", "error": f"处理消息时出错: {e}"}
                await websocket.send_text(json.dumps(error_response))

    except WebSocketDisconnect:
        print(f"WebSocket客户端断开连接: {websocket.client}")
    except Exception as e:
        print(f"WebSocket连接异常: {e}")


async def _handle_build_prompt_websocket(websocket: WebSocket, data: dict, request_id: str):
    """处理WebSocket的build_prompt请求"""
    start_time = time.time()

    try:
        session_id = data.get("session_id")
        user_query = data.get("user_query", "")
        system_resources = data.get("system_resources", "")

        if not user_query:
            raise ValueError("user_query不能为空")

        print(f"WebSocket处理build_prompt请求 - 会话: {session_id}, 查询: {user_query}")

        build_request = BuildRequest(session_id=session_id, user_query=user_query, system_resources=system_resources)
        result = await build_request_handler(build_request)

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
        reload=config.get('reload', True),
        log_level="error",
    )
