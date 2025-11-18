#!/usr/bin/env python3
"""
Mock服务 - 模拟工具服务和RAG服务
提供 /tool/get_tool_list 和 /rag/query_and_embedding 接口
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import uvicorn
import random
import json

app = FastAPI(
    title="Mock Services",
    description="模拟工具服务和RAG服务的API",
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

# ======= 请求/响应模型 =======

class RagQueryRequest(BaseModel):
    query: str = Field(..., description="用户查询")
    top_k: int = Field(3, description="返回结果数量")

class RagQueryResponse(BaseModel):
    results: List[Dict[str, Any]] = Field(..., description="RAG检索结果")
    query: str = Field(..., description="原始查询")
    total_chunks: int = Field(..., description="检索到的总块数")

# ======= Mock工具数据 =======

def get_mock_tools() -> List[Dict[str, Any]]:
    """返回OpenAI Chat格式兼容的工具定义"""
    return [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "搜索互联网获取最新信息",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词"
                        },
                        "num_results": {
                            "type": "integer",
                            "description": "返回结果数量",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function", 
            "function": {
                "name": "calculator",
                "description": "执行数学计算",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "数学表达式，如 '2+2', 'sqrt(16)'"
                        }
                    },
                    "required": ["expression"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "code_executor",
                "description": "执行Python代码",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "要执行的Python代码"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "执行超时时间（秒）",
                            "default": 30
                        }
                    },
                    "required": ["code"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "file_reader",
                "description": "读取文件内容",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "文件路径"
                        },
                        "encoding": {
                            "type": "string", 
                            "description": "文件编码",
                            "default": "utf-8"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        }
    ]

# ======= Mock RAG数据 =======

def get_mock_rag_chunks(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """返回模拟的RAG检索结果"""
    
    # 模拟知识库数据
    knowledge_base = [
        {
            "chunk": "机器学习是人工智能的一个分支，它使计算机能够从数据中学习而无需明确编程。通过算法和统计模型，机器学习系统可以识别数据中的模式并做出预测或决策。",
            "source": "ml_basics.pdf",
            "score": 0.95,
            "metadata": {"page": 12, "section": "Introduction"}
        },
        {
            "chunk": "深度学习是机器学习的一个子领域，它使用多层神经网络来模拟人脑的学习过程。深度学习在图像识别、自然语言处理和语音识别等领域取得了突破性进展。",
            "source": "deep_learning_intro.pdf", 
            "score": 0.92,
            "metadata": {"page": 5, "section": "Deep Learning Overview"}
        },
        {
            "chunk": "监督学习是机器学习中最常见的类型，它使用标记数据来训练模型。在监督学习中，每个训练样本都包含输入特征和对应的期望输出。",
            "source": "supervised_learning.pdf",
            "score": 0.88,
            "metadata": {"page": 23, "section": "Supervised Learning"}
        },
        {
            "chunk": "Python是一种高级编程语言，以其简洁的语法和强大的库生态系统而闻名。在数据科学和机器学习领域，Python是最受欢迎的语言之一。",
            "source": "python_guide.pdf",
            "score": 0.85,
            "metadata": {"page": 1, "section": "Python Introduction"}
        },
        {
            "chunk": "神经网络由相互连接的节点（神经元）组成，这些节点按层排列：输入层、隐藏层和输出层。每个连接都有权重，网络通过调整这些权重来学习。",
            "source": "neural_networks.pdf",
            "score": 0.83,
            "metadata": {"page": 8, "section": "Neural Network Architecture"}
        }
    ]
    
    # 根据查询内容模拟相关性评分
    query_lower = query.lower()
    scored_chunks = []
    
    for chunk in knowledge_base:
        # 简单的相关性评分逻辑
        relevance_score = chunk["score"]
        
        # 根据查询关键词调整分数
        if "python" in query_lower and "python" in chunk["chunk"].lower():
            relevance_score += 0.1
        if "机器学习" in query_lower or "machine learning" in query_lower:
            if "机器学习" in chunk["chunk"] or "machine learning" in chunk["chunk"].lower():
                relevance_score += 0.15
        if "深度学习" in query_lower or "deep learning" in query_lower:
            if "深度学习" in chunk["chunk"] or "deep learning" in chunk["chunk"].lower():
                relevance_score += 0.12
        
        # 添加一些随机性使结果更真实
        relevance_score += random.uniform(-0.05, 0.05)
        relevance_score = min(1.0, relevance_score)  # 确保不超过1.0
        
        scored_chunk = chunk.copy()
        scored_chunk["score"] = round(relevance_score, 3)
        scored_chunks.append(scored_chunk)
    
    # 按分数排序并返回top_k个结果
    scored_chunks.sort(key=lambda x: x["score"], reverse=True)
    return scored_chunks[:top_k]

# ======= API路由 =======

@app.get("/tool/get_tool_list", response_model=Dict[str, Any])
async def get_tool_list():
    """获取可用工具列表 - OpenAI Chat格式"""
    tools = get_mock_tools()
    
    return {
        "tools": tools,
        "count": len(tools),
        "timestamp": "2024-01-01T00:00:00Z",
        "status": "active"
    }

@app.post("/rag/query_and_embedding", response_model=RagQueryResponse)
async def query_and_embedding(request: RagQueryRequest):
    """RAG查询接口 - 返回相关知识块"""
    
    query = request.query
    top_k = request.top_k
    
    # 获取模拟的RAG结果
    results = get_mock_rag_chunks(query, top_k)
    
    return RagQueryResponse(
        results=results,
        query=query,
        total_chunks=len(results)
    )

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "services": {
            "tool_service": "active",
            "rag_service": "active"
        },
        "timestamp": "2024-01-01T00:00:00Z"
    }

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Mock Services API",
        "version": "1.0.0",
        "endpoints": [
            "/tool/get_tool_list",
            "/rag/query_and_embedding", 
            "/health"
        ]
    }

# ======= 启动服务 =======

if __name__ == "__main__":
    print("启动Mock服务...")
    print("可用接口:")
    print("  - GET  /tool/get_tool_list")
    print("  - POST /rag/query_and_embedding")
    print("  - GET  /health")
    print("\n服务运行在: http://localhost:2345")
    
    uvicorn.run(
        "mock_services:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )