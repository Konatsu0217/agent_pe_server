#!/usr/bin/env python3
"""
测试上游服务 - 演示如何调用上游服务的接口
"""

import requests
import json
import time

def test_chat_flow():
    """测试完整的聊天流程"""
    
    base_url = "http://localhost:8080"
    
    print("=== 测试上游服务 ===")
    print(f"服务地址: {base_url}")
    
    # 1. 检查服务状态
    print("\n1. 检查服务状态")
    try:
        response = requests.get(f"{base_url}/health")
        if response.status_code == 200:
            health_data = response.json()
            print(f"✓ 上游服务状态: {health_data['status']}")
            print(f"✓ PE Server状态: {health_data['pe_server_status']}")
            print(f"✓ 活跃会话数: {health_data['active_sessions']}")
        else:
            print(f"✗ 健康检查失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 无法连接上游服务: {e}")
        return
    
    # 2. 开始新的聊天会话
    print("\n2. 开始新的聊天会话")
    test_messages = [
        "你好，我想了解机器学习",
        "什么是深度学习？它与机器学习有什么区别？",
        "你能给我推荐一些学习资源吗？",
        "Python在机器学习中的作用是什么？",
        "谢谢你的帮助！"
    ]
    
    session_id = None
    
    for i, message in enumerate(test_messages, 1):
        print(f"\n--- 对话轮次 {i} ---")
        print(f"用户: {message}")
        
        try:
            # 发送聊天请求
            chat_data = {
                "message": message,
                "session_id": session_id,
                "system_prompt": "你是一个专业的AI助手，擅长解释机器学习和深度学习概念。"
            }
            
            response = requests.post(
                f"{base_url}/chat",
                json=chat_data,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                session_id = result.get("session_id", session_id)
                assistant_response = result.get("response", "")
                estimated_tokens = result.get("estimated_tokens", 0)
                
                print(f"助手: {assistant_response}")
                print(f"会话ID: {session_id}")
                print(f"估算token数: {estimated_tokens}")
                
                # 显示一些调试信息
                if result.get("llm_request"):
                    llm_req = result["llm_request"]
                    print(f"使用的工具数: {len(llm_req.get('tools', []))}")
                    print(f"消息数: {len(llm_req.get('messages', []))}")
                
            else:
                print(f"✗ 聊天请求失败: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"✗ 请求异常: {e}")
        
        # 小延迟，模拟真实对话
        time.sleep(0.5)
    
    # 3. 查看会话历史
    print(f"\n3. 查看会话历史 (会话ID: {session_id})")
    try:
        response = requests.get(f"{base_url}/session/{session_id}")
        if response.status_code == 200:
            session_info = response.json()
            print(f"会话消息数: {session_info['message_count']}")
            print(f"创建时间: {session_info['created_at']}")
            print(f"最后活动: {session_info['last_activity']}")
            
            print("\n对话历史:")
            for i, msg in enumerate(session_info['messages'], 1):
                role_emoji = "👤" if msg['role'] == 'user' else "🤖" if msg['role'] == 'assistant' else "⚙️"
                print(f"{i}. {role_emoji} {msg['role']}: {msg['content'][:50]}...")
        else:
            print(f"✗ 获取会话信息失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 获取会话信息异常: {e}")
    
    # 4. 列出所有会话
    print("\n4. 列出所有会话")
    try:
        response = requests.get(f"{base_url}/sessions")
        if response.status_code == 200:
            sessions_data = response.json()
            print(f"总会话数: {sessions_data['total']}")
            for session in sessions_data['sessions']:
                print(f"- 会话ID: {session['session_id'][:8]}...")
                print(f"  消息数: {session['message_count']}")
                print(f"  创建时间: {session['created_at']}")
                print(f"  最后活动: {session['last_activity']}")
    except Exception as e:
        print(f"✗ 列出会话异常: {e}")

def test_direct_pe_server_call():
    """直接测试PE Server的build_request接口"""
    
    print("\n\n=== 直接测试PE Server ===")
    
    pe_server_url = "http://localhost:25535"
    
    # 测试build_request接口
    print("\n1. 测试build_request接口")
    try:
        build_request_data = {
            "session_id": "test_session_123",
            "user_query": "什么是机器学习？"
        }
        
        response = requests.post(
            f"{pe_server_url}/api/build_request",
            json=build_request_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✓ build_request接口调用成功")
            print(f"估算token数: {result.get('estimated_tokens', 0)}")
            print(f"历史轮次: {result.get('trimmed_history_rounds', 0)}")
            
            llm_request = result.get('llm_request', {})
            print(f"模型: {llm_request.get('model', 'unknown')}")
            print(f"消息数: {len(llm_request.get('messages', []))}")
            print(f"工具数: {len(llm_request.get('tools', []))}")
            
            # 显示消息内容
            if llm_request.get('messages'):
                print("\n消息内容:")
                for i, msg in enumerate(llm_request['messages'], 1):
                    print(f"{i}. [{msg.get('role', 'unknown')}] {msg.get('content', '')[:60]}...")
            
            # 显示工具定义
            if llm_request.get('tools'):
                print("\n可用工具:")
                for i, tool in enumerate(llm_request['tools'], 1):
                    if "function" in tool:
                        func = tool["function"]
                        print(f"{i}. {func.get('name', 'unknown')}: {func.get('description', '')[:50]}...")
        else:
            print(f"✗ build_request接口调用失败: {response.status_code} - {response.text}")
            
    except Exception as e:
        print(f"✗ 调用异常: {e}")

def test_mock_services():
    """测试Mock服务"""
    
    print("\n\n=== 测试Mock服务 ===")
    
    mock_services_url = "http://localhost:8000"
    
    # 测试工具接口
    print("\n1. 测试工具接口")
    try:
        response = requests.get(f"{mock_services_url}/tool/get_tool_list")
        if response.status_code == 200:
            tools_data = response.json()
            print(f"✓ 工具接口正常，返回{tools_data['count']}个工具")
            for i, tool in enumerate(tools_data['tools'], 1):
                if "function" in tool:
                    func = tool["function"]
                    print(f"{i}. {func.get('name', 'unknown')}: {func.get('description', '')[:40]}...")
        else:
            print(f"✗ 工具接口异常: {response.status_code}")
    except Exception as e:
        print(f"✗ 工具接口异常: {e}")
    
    # 测试RAG接口
    print("\n2. 测试RAG接口")
    try:
        rag_query_data = {
            "query": "机器学习的基本概念",
            "top_k": 3
        }
        
        response = requests.post(
            f"{mock_services_url}/rag/query_and_embedding",
            json=rag_query_data,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            rag_data = response.json()
            print(f"✓ RAG接口正常，返回{rag_data['total_chunks']}个结果")
            print(f"查询: {rag_data['query']}")
            
            for i, result in enumerate(rag_data['results'], 1):
                print(f"\n{i}. 分数: {result.get('score', 0)}")
                print(f"   来源: {result.get('source', 'unknown')}")
                print(f"   内容: {result.get('chunk', '')[:80]}...")
        else:
            print(f"✗ RAG接口异常: {response.status_code}")
            
    except Exception as e:
        print(f"✗ RAG接口异常: {e}")

if __name__ == "__main__":
    print("开始测试上游服务和相关组件...")
    print("请确保以下服务正在运行:")
    print("  - Mock服务: python mock_services.py (端口8000)")
    print("  - PE Server: python pe_core.py (端口18080)")
    print("  - 上游服务: python upstream_service.py (端口8080)")
    print()
    
    input("按Enter键开始测试...")
    
    # 运行测试
    test_chat_flow()
    test_direct_pe_server_call()
    test_mock_services()
    
    print("\n\n=== 测试完成 ===")
    print("所有测试已执行完毕。请查看上面的输出结果。")