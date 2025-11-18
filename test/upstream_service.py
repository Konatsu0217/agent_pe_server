#!/usr/bin/env python3
"""
上游服务 - 模拟调用pe_server的build_request接口
提供用户友好的聊天界面，内部调用pe_server的build_request接口
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import httpx
import asyncio
import uuid
import time
import uvicorn
from datetime import datetime

app = FastAPI(
    title="上游服务 - Upstream Service",
    description="模拟上游应用，调用pe_server的build_request接口",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======= 配置 =======
PE_SERVER_URL = "http://localhost:18080"  # pe_core服务的地址

# ======= 请求/响应模型 =======

class ChatMessage(BaseModel):
    role: str = Field(..., description="消息角色: user, assistant, system")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[str] = Field(None, description="时间戳")

class ChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    session_id: Optional[str] = Field(None, description="会话ID，用于保持对话历史")
    system_prompt: Optional[str] = Field(None, description="系统提示词")

class ChatResponse(BaseModel):
    response: str = Field(..., description="助手回复")
    session_id: str = Field(..., description="会话ID")
    llm_request: Optional[Dict[str, Any]] = Field(None, description="发送给LLM的请求体")
    estimated_tokens: Optional[int] = Field(None, description="估算的token数量")
    timestamp: str = Field(..., description="响应时间戳")

class SessionInfo(BaseModel):
    session_id: str
    message_count: int
    created_at: str
    last_activity: str
    messages: List[ChatMessage]

# ======= 会话管理 =======

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, List[ChatMessage]] = {}
    
    def get_or_create_session(self, session_id: Optional[str]) -> str:
        """获取或创建会话"""
        if session_id is None or session_id not in self.sessions:
            new_session_id = str(uuid.uuid4())
            self.sessions[new_session_id] = []
            return new_session_id
        return session_id
    
    def add_message(self, session_id: str, role: str, content: str):
        """添加消息到会话历史"""
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        
        message = ChatMessage(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat()
        )
        self.sessions[session_id].append(message)
    
    def get_session_history(self, session_id: str, max_rounds: int = 10) -> List[Dict[str, str]]:
        """获取会话历史，转换为pe_server需要的格式"""
        if session_id not in self.sessions:
            return []
        
        messages = self.sessions[session_id][-max_rounds*2:]  # 每轮包含user和assistant两条消息
        return [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
    
    def get_session_info(self, session_id: str) -> Optional[SessionInfo]:
        """获取会话信息"""
        if session_id not in self.sessions:
            return None
        
        messages = self.sessions[session_id]
        if not messages:
            return None
        
        return SessionInfo(
            session_id=session_id,
            message_count=len(messages),
            created_at=messages[0].timestamp if messages else datetime.now().isoformat(),
            last_activity=messages[-1].timestamp if messages else datetime.now().isoformat(),
            messages=messages
        )

# 创建会话管理器实例
session_manager = SessionManager()

# ======= PE Server客户端 =======

class PEServerClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def build_request(self, session_id: str, user_query: str) -> Dict[str, Any]:
        """调用pe_server的build_request接口"""
        
        url = f"{self.base_url}/api/build_request"
        payload = {
            "session_id": session_id,
            "user_query": user_query
        }
        
        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=500, detail=f"PE Server请求失败: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"处理响应失败: {str(e)}")
    
    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()

# 创建PE Server客户端
pe_client = PEServerClient(PE_SERVER_URL)

# ======= 聊天逻辑 =======

async def process_chat(message: str, session_id: Optional[str], system_prompt: Optional[str] = None) -> ChatResponse:
    """处理聊天请求"""
    
    # 获取或创建会话
    session_id = session_manager.get_or_create_session(session_id)
    
    # 如果有系统提示词，添加到会话开始
    if system_prompt and len(session_manager.sessions.get(session_id, [])) == 0:
        session_manager.add_message(session_id, "system", system_prompt)
    
    # 添加用户消息
    session_manager.add_message(session_id, "user", message)
    
    # 调用pe_server构建LLM请求
    try:
        pe_response = await pe_client.build_request(session_id, message)
        
        # 模拟LLM响应（实际应用中这里会调用真实的LLM）
        llm_request = pe_response.get("llm_request", {})
        estimated_tokens = pe_response.get("estimated_tokens", 0)
        trimmed_rounds = pe_response.get("trimmed_history_rounds", 0)
        
        # 模拟LLM生成回复
        mock_response = generate_mock_llm_response(message, llm_request)
        
        # 添加助手回复到会话历史
        session_manager.add_message(session_id, "assistant", mock_response)
        
        return ChatResponse(
            response=mock_response,
            session_id=session_id,
            llm_request=llm_request,
            estimated_tokens=estimated_tokens,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        # 如果pe_server不可用，提供降级回复
        fallback_response = generate_fallback_response(message)
        session_manager.add_message(session_id, "assistant", fallback_response)
        
        return ChatResponse(
            response=fallback_response,
            session_id=session_id,
            llm_request={},
            estimated_tokens=len(message.split()) * 2,  # 粗略估算
            timestamp=datetime.now().isoformat()
        )

def generate_mock_llm_response(user_message: str, llm_request: Dict[str, Any]) -> str:
    """模拟LLM生成回复"""
    
    # 根据用户消息生成相关回复
    user_lower = user_message.lower()
    
    if "你好" in user_lower or "hello" in user_lower:
        return "你好！我是AI助手，很高兴为你提供帮助。有什么我可以协助你的吗？"
    
    elif "机器学习" in user_lower or "machine learning" in user_lower:
        return "机器学习是人工智能的一个重要分支，它让计算机能够从数据中学习并做出预测或决策，而无需明确编程。你想了解机器学习的哪个方面呢？"
    
    elif "深度学习" in user_lower or "deep learning" in user_lower:
        return "深度学习是机器学习的一个子领域，使用多层神经网络来模拟人脑的学习过程。它在图像识别、自然语言处理等领域取得了突破性进展。"
    
    elif "python" in user_lower:
        return "Python是一种高级编程语言，以其简洁的语法和强大的库生态系统而闻名。在数据科学和机器学习领域，Python是最受欢迎的语言之一。"
    
    elif "工具" in user_lower or "tool" in user_lower:
        tools_info = []
        if llm_request.get("tools"):
            tools_info.append(f"我当前可用的工具有：{len(llm_request['tools'])}个")
            for tool in llm_request["tools"][:3]:  # 显示前3个工具
                if "function" in tool:
                    tools_info.append(f"- {tool['function'].get('name', 'unknown')}: {tool['function'].get('description', '')}")
        
        if tools_info:
            return "我可以使用多种工具来帮助你：\\n" + "\\n".join(tools_info)
        else:
            return "我可以帮助你回答问题、进行分析和提供建议。请告诉我你需要什么帮助。"
    
    else:
        # 通用回复
        return f"我理解你在问：{user_message}。让我为你提供一些相关信息...\\n\\n基于我的知识，这是一个很有意思的问题。如果你有更具体的需求，请随时告诉我。"

def generate_fallback_response(message: str) -> str:
    """生成降级回复（当PE Server不可用时）"""
    return f"我收到了你的消息：{message}。目前服务正在处理中，请稍后重试。"

# ======= API路由 =======

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """聊天接口"""
    try:
        response = await process_chat(request.message, request.session_id, request.system_prompt)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理聊天请求失败: {str(e)}")

@app.get("/session/{session_id}", response_model=SessionInfo)
async def get_session(session_id: str):
    """获取会话信息"""
    session_info = session_manager.get_session_info(session_id)
    if not session_info:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session_info

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    if session_id in session_manager.sessions:
        del session_manager.sessions[session_id]
        return {"message": "会话已删除", "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail="会话不存在")

@app.get("/sessions")
async def list_sessions():
    """列出所有会话"""
    sessions = []
    for session_id in session_manager.sessions.keys():
        session_info = session_manager.get_session_info(session_id)
        if session_info:
            sessions.append({
                "session_id": session_id,
                "message_count": session_info.message_count,
                "created_at": session_info.created_at,
                "last_activity": session_info.last_activity
            })
    return {"sessions": sessions, "total": len(sessions)}

@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        # 检查PE Server是否可用
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{PE_SERVER_URL}/health")
            pe_status = "healthy" if response.status_code == 200 else "unhealthy"
    except:
        pe_status = "unreachable"
    
    return {
        "status": "healthy",
        "pe_server_status": pe_status,
        "active_sessions": len(session_manager.sessions),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "上游服务 - Upstream Service",
        "version": "1.0.0",
        "endpoints": [
            "POST /chat - 聊天接口",
            "GET /session/{session_id} - 获取会话信息",
            "DELETE /session/{session_id} - 删除会话",
            "GET /sessions - 列出所有会话",
            "GET /health - 健康检查"
        ],
        "pe_server_url": PE_SERVER_URL
    }

# ======= 启动和清理 =======

@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    await pe_client.close()

if __name__ == "__main__":
    print("启动上游服务...")
    print(f"PE Server地址: {PE_SERVER_URL}")
    print("可用接口:")
    print("  - POST /chat")
    print("  - GET  /session/{session_id}")
    print("  - DELETE /session/{session_id}")
    print("  - GET  /sessions")
    print("  - GET  /health")
    print("\n服务运行在: http://localhost:8080")
    
    uvicorn.run(
        "upstream_service:app",
        host="0.0.0.0",
        port=8080,
        reload=True
    )