from typing import List, Dict, Any, Optional
from pathlib import Path
import time
from functools import wraps
import asyncio

import httpx
import tiktoken

from config_manager import ConfigManager

# 获取配置和会话历史
config = ConfigManager.get_config()


# ======= 非侵入式耗时监控装饰器 =======
def timeit(name: str):
    """非侵入式耗时监控装饰器"""
    def decorator(func):
        if asyncio.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = await func(*args, **kwargs)
                    return result
                finally:
                    cost = time.time() - start
                    print(f"[{name}] 耗时: {cost:.3f}s")
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start = time.time()
                try:
                    result = func(*args, **kwargs)
                    return result
                finally:
                    cost = time.time() - start
                    print(f"[{name}] 耗时: {cost:.3f}s")
            return sync_wrapper
    return decorator


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
def load_system_prompt(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return ""  # 允许为空，但建议警告
    return p.read_text(encoding="utf-8")


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


# ======= util: call rag =======
async def call_rag(client: httpx.AsyncClient, query: str, top_k: int) -> List[Dict[str, Any]]:
    if not config['pe_enable_rag']:
        return []
    payload = {"query": query, "top_k": top_k}
    try:
        resp = await client.post(config['pe_rag_service_url'], json=payload, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", []) if isinstance(data, dict) else []
    except Exception as e:
        print(f"rag call failed: {e}")
        return []


# ======= util: 获取会话历史记录 =======
async def fetch_session_history(client: httpx.AsyncClient, session_id: Optional[str]) -> List[Dict[str, str]]:
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
            return messages
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


# ======= util: build rag system prompt from chunks =======
def rag_chunks_to_system_prompt(chunks: List[Dict[str, Any]]) -> Optional[Dict[str, str]]:
    if not chunks:
        return None
    lines = ["RAG Retrieved Knowledge Chunks:"]
    for i, c in enumerate(chunks, start=1):
        chunk_text = c.get("chunk") or c.get("text") or ""
        source = c.get("source") or c.get("id") or "unknown"
        score = c.get("score")
        if score is not None:
            lines.append(f"{i}. (score={score}) source={source} -- {chunk_text}")
        else:
            lines.append(f"{i}. source={source} -- {chunk_text}")
    return {"role": "system", "content": "\n".join(lines)}


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
