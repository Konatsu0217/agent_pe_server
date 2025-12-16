import json
from typing import List, Dict, Any, Optional, Coroutine
from pathlib import Path
import time
from functools import wraps
import asyncio

import httpx
import tiktoken
from pydantic import BaseModel, Field

from config_manager import ConfigManager

class CacheManager:
    def __init__(self):
        self._cache = dict()
        self._cache_lock = asyncio.Lock()

    async def cache_prompt(self, session_id: str, system_prompt: str, tools_prompt: str):
        async with self._cache_lock:
            self._cache[session_id] = {
                'system_prompt': system_prompt,
                'tools_prompt': tools_prompt
            }

    async def update_cache(self, session_id: str, system_prompt: str, tools_prompt: str):
        async with self._cache_lock:
            if session_id in self._cache:
                self._cache[session_id]['system_prompt'] = system_prompt
                self._cache[session_id]['tools_prompt'] = tools_prompt

    async def get_cached_prompt(self, session_id: str) -> Optional[Dict[str, str]]:
        async with self._cache_lock:
            return self._cache.get(session_id, None)


# 获取配置和会话历史
config = ConfigManager.get_config()
cache_manager = CacheManager()

# ======= 零入侵异步任务监控器 =======
async def monitor_task(task, name: str):
    """监控异步任务的执行时间，零入侵版本"""
    start = time.time()
    try:
        result = await task
        return result
    finally:
        cost = time.time() - start
        print(f"[{name}] 耗时: {cost:.3f}s")


def monitor_thread_task(func, args=(), name: str = ""):
    """监控线程任务的执行时间，零入侵版本"""
    start = time.time()
    try:
        result = func(*args)
        return result
    finally:
        cost = time.time() - start
        print(f"[{name}] 耗时: {cost:.3f}s")

# try to use tiktoken for better token estimation; fallback to crude estimator
try:
    import tiktoken
    _HAS_TIKTOKEN = True
except Exception:
    _HAS_TIKTOKEN = False


# ======= util: load system prompt =======
def load_system_prompt(path: str, session_id: str) -> str:
    """加载系统提示词，支持缓存"""
    cached_prompt = asyncio.run(cache_manager.get_cached_prompt(session_id))
    if cached_prompt:
        return cached_prompt['system_prompt']

    p = Path(Path(__file__).resolve().parent / path)
    if not p.exists():
        return ""  # 允许为空，但建议警告
    system_prompt = p.read_text(encoding="utf-8")
    asyncio.run(cache_manager.cache_prompt(session_id, system_prompt, ""))
    return system_prompt


# ======= util: tool discovery =======
async def discover_tools(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    if not config['pe_enable_tools']:
        return []
    try:
        resp = await client.get(config['pe_tool_service_url'], timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        # 期待 {"tools": [...]} 格式
        return data.get("tools", []) if isinstance(data, dict) else []
    except Exception as e:
        # 不要抛错，返回空并打印日志
        print(f"tool discovery failed: {e}")
        return []




# ======= util: 获取会话历史记录 =======
async def fetch_session_history(client: httpx.AsyncClient, session_id: Optional[str], trimmed_history_rounds: int) -> List[Dict[str, str]]:
    """从外部服务获取会话历史记录"""
    if not session_id or not config.get('pe_session_history_service_url') or not config['pe_enable_history']:
        return []
    
    try:
        url = f"{config['pe_session_history_service_url']}/{session_id}"
        resp = await client.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        
        # 期待返回格式: {"messages": [{"role": "user", "content": "..."}, ...]}
        messages = data.get("messages", [])
        if isinstance(messages, list):
            return messages[-trimmed_history_rounds*2:]  # 每条对话包含user和assistant两条消息
        return []
    except Exception as e:
        print(f"fetch session history failed: {e}")
        return []


# ======= util: token estimate =======
def estimate_tokens_from_messages(messages: List[Dict[str, str]]) -> int:
    # 优先使用 tiktoken（如果可用），否则用简单字数估计
    full_text = "".join(m.get("content", "") for m in messages)
    if _HAS_TIKTOKEN:
        try:
            enc = tiktoken.encoding_for_model("gpt-4")
        except Exception:
            enc = tiktoken.get_encoding("cl100k_base")
        toks = len(enc.encode(full_text))
        return toks
    else:
        # 粗略估算：1 token ~= 4 characters
        return max(1, len(full_text) // 4)




# ======= util: trim history to rounds =======
def get_history_for_session(session_id: Optional[str], keep_rounds: int) -> List[Dict[str, str]]:
    if not config['pe_enable_history'] or not session_id:
        return []
    # hist = _SESSION_HISTORY.get(session_id, [])
    hist = []
    # history is stored as alternating user/assistant messages
    # keep_rounds 表示用户-助手对话对数
    max_messages = keep_rounds * 2
    if len(hist) <= max_messages:
        return hist.copy()
    else:
        return hist[-max_messages:]


# ======= util: compress assistant messages (简单摘要策略) =======
# production 可接入 summarization model

def compress_assistant_messages(messages: List[Dict[str, str]], target_chars: int = 800) -> List[Dict[str, str]]:
    # 将长的 assistant 消息压缩为一段短文本（简单截断或抽取首尾）
    out = []
    for m in messages:
        if m.get("role") == "assistant":
            text = m.get("content", "")
            if len(text) > target_chars:
                compressed = text[: target_chars//2].rstrip() + " ... " + text[-target_chars//2 :].lstrip()
                out.append({"role": "assistant", "content": f"[COMPRESSED] {compressed}"})
            else:
                out.append(m)
        else:
            out.append(m)
    return out



# ======= 请求 / 响应 模型 ========
class BuildRequest(BaseModel):
    session_id: Optional[str] = Field(None, description="会话ID，用于从缓存中获取历史")
    user_query: str = Field(..., description="用户当前 query")
    system_resources: Optional[str] = Field(None, description="系统中的可变资源")


class BuildResponse(BaseModel):
    llm_request: Dict[str, Any]
    estimated_tokens: int


# ======= WebSocket 消息模型 ========
class WebSocketBuildPromptRequest(BaseModel):
    """WebSocket build_prompt 请求"""
    session_id: Optional[str] = Field(None, description="会话ID")
    user_query: str = Field(..., description="用户查询")
    request_id: str = Field(..., description="请求ID，用于匹配响应")
    stream: bool = Field(False, description="是否流式响应")


class WebSocketBuildPromptResponse(BaseModel):
    """WebSocket build_prompt 响应"""
    request_id: str = Field(..., description="对应的请求ID")
    llm_request: Dict[str, Any] = Field(..., description="LLM请求体")
    estimated_tokens: int = Field(..., description="估算的token数量")
    trimmed_history_rounds: int = Field(..., description="裁剪的历史轮数")
    processing_time_ms: float = Field(..., description="处理时间（毫秒）")


class WebSocketErrorResponse(BaseModel):
    """WebSocket错误响应"""
    request_id: Optional[str] = Field(None, description="对应的请求ID")
    error_type: str = Field(..., description="错误类型")
    error_message: str = Field(..., description="错误消息")
    timestamp: float = Field(default_factory=time.time, description="错误时间戳")
