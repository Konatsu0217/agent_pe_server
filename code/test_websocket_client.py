#!/usr/bin/env python3
"""
WebSocket客户端测试脚本
用于测试PE Server的WebSocket接口功能
"""

import asyncio
import json
import time
import websockets
from typing import Optional


class PEWebSocketClient:
    """PE Server WebSocket客户端"""
    
    def __init__(self, uri: str = "ws://127.0.0.1:25535/ws/build_prompt"):
        self.uri = uri
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connected = False
        self.request_counter = 0
    
    async def connect(self):
        """连接到WebSocket服务器"""
        try:
            self.websocket = await websockets.connect(self.uri)
            self.connected = True
            print(f"✅ 已连接到WebSocket服务器: {self.uri}")
            return True
        except Exception as e:
            print(f"❌ 连接WebSocket服务器失败: {e}")
            return False
    
    async def disconnect(self):
        """断开WebSocket连接"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            print("🔌 WebSocket连接已断开")
    
    def _generate_request_id(self) -> str:
        """生成唯一的请求ID"""
        self.request_counter += 1
        return f"req_{int(time.time() * 1000)}_{self.request_counter}"
    
    async def send_build_prompt_request(self, user_query: str, session_id: Optional[str] = None, stream: bool = False) -> dict:
        """
        发送build_prompt请求
        
        Args:
            user_query: 用户查询内容
            session_id: 会话ID（可选）
            stream: 是否流式响应
            
        Returns:
            响应数据
        """
        if not self.connected or not self.websocket:
            raise RuntimeError("WebSocket未连接")
        
        request_id = self._generate_request_id()
        
        # 构建请求消息
        request_message = {
            "type": "build_prompt",
            "request_id": request_id,
            "data": {
                "user_query": user_query,
                "session_id": session_id,
                "stream": stream
            }
        }
        
        print(f"📤 发送请求 - ID: {request_id}")
        print(f"   查询: {user_query}")
        if session_id:
            print(f"   会话: {session_id}")
        
        # 发送请求
        await self.websocket.send(json.dumps(request_message))
        
        # 等待响应
        response_text = await self.websocket.recv()
        response_data = json.loads(response_text)
        
        print(f"📥 收到响应 - ID: {response_data.get('request_id')}")
        print(f"   状态: {response_data.get('status')}")
        
        if response_data.get('status') == 'success':
            data = response_data.get('data', {})
            print(f"   Token数量: {data.get('estimated_tokens')}")
            print(f"   历史轮数: {data.get('trimmed_history_rounds')}")
            print(f"   处理时间: {data.get('processing_time_ms', 0):.2f}ms")
            print(f"   消息数量: {len(data.get('llm_request', {}).get('messages', []))}")
        else:
            print(f"   错误: {response_data.get('error')}")
        
        return response_data
    
    async def send_ping(self) -> dict:
        """发送ping消息"""
        if not self.connected or not self.websocket:
            raise RuntimeError("WebSocket未连接")
        
        request_id = self._generate_request_id()
        
        ping_message = {
            "type": "ping",
            "request_id": request_id
        }
        
        print(f"🏓 发送ping - ID: {request_id}")
        await self.websocket.send(json.dumps(ping_message))
        
        # 等待pong响应
        response_text = await self.websocket.recv()
        response_data = json.loads(response_text)
        
        if response_data.get('type') == 'pong':
            print(f"🏓 收到pong - ID: {response_data.get('request_id')}")
        
        return response_data
    
    async def test_multiple_requests(self, queries: list, session_id: Optional[str] = None):
        """测试多个请求"""
        print(f"\n🧪 开始测试多个请求（共{len(queries)}个）")
        
        results = []
        for i, query in enumerate(queries, 1):
            print(f"\n--- 测试 {i}/{len(queries)} ---")
            try:
                result = await self.send_build_prompt_request(query, session_id)
                results.append(result)
                
                # 短暂延迟，避免请求过快
                if i < len(queries):
                    await asyncio.sleep(0.5)
            
            except Exception as e:
                print(f"请求失败: {e}")
                results.append(None)
        
        # 统计结果
        successful = sum(1 for r in results if r and r.get('status') == 'success')
        print(f"\n📊 测试结果: {successful}/{len(queries)} 个请求成功")
        
        return results


async def main():
    """主测试函数"""
    # 创建客户端
    client = PEWebSocketClient()
    
    # 连接到服务器
    if not await client.connect():
        return
    
    try:
        # 测试1: 简单查询
        print("\n" + "="*50)
        print("测试1: 简单查询")
        print("="*50)
        await client.send_build_prompt_request("你好，请介绍一下机器学习")
        
        # 测试2: 带会话ID的查询
        print("\n" + "="*50)
        print("测试2: 带会话ID的查询")
        print("="*50)
        session_id = "test_session_001"
        await client.send_build_prompt_request("什么是深度学习？", session_id=session_id)
        await client.send_build_prompt_request("它有哪些应用场景？", session_id=session_id)
        
        # 测试3: 编程相关问题
        print("\n" + "="*50)
        print("测试3: 编程相关问题")
        print("="*50)
        await client.send_build_prompt_request("帮我写一段Python代码来计算斐波那契数列")
        
        # 测试4: ping/pong
        print("\n" + "="*50)
        print("测试4: Ping/Pong测试")
        print("="*50)
        await client.send_ping()
        
        # 测试5: 多个请求连续发送
        print("\n" + "="*50)
        print("测试5: 多个请求连续发送")
        print("="*50)
        test_queries = [
            "什么是人工智能？",
            "人工智能和机器学习有什么区别？",
            "深度学习需要哪些基础知识？",
            "推荐一些机器学习的入门书籍"
        ]
        await client.test_multiple_requests(test_queries, session_id="batch_test_session")
        
        # 等待一段时间，保持连接
        print("\n⏳ 保持连接10秒...")
        await asyncio.sleep(10)
        
    except KeyboardInterrupt:
        print("\n🛑 用户中断测试")
    
    except Exception as e:
        print(f"\n❌ 测试过程中出错: {e}")
    
    finally:
        # 断开连接
        await client.disconnect()


if __name__ == "__main__":
    print("🚀 PE Server WebSocket客户端测试")
    print("="*60)
    print("确保PE Server已启动并运行在 ws://127.0.0.1:25535/ws/build_prompt")
    print("="*60)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 程序被用户终止")