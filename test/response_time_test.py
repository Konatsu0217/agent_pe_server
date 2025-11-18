import time
import requests
import json
import statistics
from datetime import datetime
import sys

class ResponseTimeTest:
    def __init__(self, base_url="http://127.0.0.1:25535"):
        self.base_url = base_url
        self.api_endpoint = f"{base_url}/api/build_request"
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
        
        # 不同类型的测试查询
        self.test_queries = [
            {
                "name": "简单问候",
                "query": "你好",
                "expected_complexity": "低"
            },
            {
                "name": "基础问题", 
                "query": "今天天气怎么样？",
                "expected_complexity": "低"
            },
            {
                "name": "技术问题",
                "query": "什么是机器学习？",
                "expected_complexity": "中"
            },
            {
                "name": "编程问题",
                "query": "帮我写一段Python代码来计算斐波那契数列",
                "expected_complexity": "高"
            },
            {
                "name": "复杂问题",
                "query": "解释一下量子计算的原理和应用场景",
                "expected_complexity": "高"
            }
        ]
    
    def check_service_health(self):
        """检查服务是否正常运行"""
        try:
            response = self.session.get(f"{self.base_url}/docs", timeout=5)
            return response.status_code == 200
        except Exception as e:
            print(f"服务检查失败: {e}")
            return False
    
    def send_single_request(self, query, session_id=None):
        """发送单个请求并返回响应时间"""
        start_time = time.time()
        
        payload = {
            "session_id": session_id,
            "user_query": query
        }
        
        try:
            response = self.session.post(
                self.api_endpoint,
                json=payload,
                timeout=10
            )
            
            end_time = time.time()
            response_time = (end_time - start_time) * 1000  # 转换为毫秒
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "success": True,
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "estimated_tokens": result.get('estimated_tokens', 0),
                    "trimmed_history_rounds": result.get('trimmed_history_rounds', 0)
                }
            else:
                return {
                    "success": False,
                    "response_time": response_time,
                    "status_code": response.status_code,
                    "error": f"HTTP {response.status_code}"
                }
                
        except Exception as e:
            end_time = time.time()
            response_time = (end_time - start_time) * 1000
            return {
                "success": False,
                "response_time": response_time,
                "error": str(e)
            }
    
    def test_single_user_sequential(self, requests_per_query=5):
        """测试单用户顺序请求的响应时间"""
        print("\n=== 单用户顺序请求测试 ===")
        print(f"每个查询类型发送 {requests_per_query} 个请求")
        
        results = {}
        
        for query_info in self.test_queries:
            query_name = query_info["name"]
            query_text = query_info["query"]
            complexity = query_info["expected_complexity"]
            
            print(f"\n--- 测试: {query_name} (复杂度: {complexity}) ---")
            
            response_times = []
            session_id = f"test_session_{int(time.time())}"
            
            for i in range(requests_per_query):
                print(f"  请求 {i+1}/{requests_per_query}", end="")
                
                result = self.send_single_request(query_text, session_id)
                
                if result["success"]:
                    response_times.append(result["response_time"])
                    print(f" -> {result['response_time']:.2f}ms (tokens: {result['estimated_tokens']})")
                else:
                    print(f" -> 失败: {result['error']}")
            
            if response_times:
                results[query_name] = {
                    "complexity": complexity,
                    "response_times": response_times,
                    "avg_time": statistics.mean(response_times),
                    "min_time": min(response_times),
                    "max_time": max(response_times),
                    "median_time": statistics.median(response_times)
                }
                
                print(f"  平均响应时间: {results[query_name]['avg_time']:.2f}ms")
                print(f"  最小/最大: {results[query_name]['min_time']:.2f}ms / {results[query_name]['max_time']:.2f}ms")
        
        return results
    
    def test_cold_start(self):
        """测试冷启动响应时间"""
        print("\n=== 冷启动测试 ===")
        print("测试第一个请求的响应时间（冷启动）")
        
        # 等待几秒确保服务"冷却"
        time.sleep(2)
        
        result = self.send_single_request("你好，测试冷启动")
        
        if result["success"]:
            print(f"冷启动响应时间: {result['response_time']:.2f}ms")
            print(f"Token数量: {result['estimated_tokens']}")
        else:
            print(f"冷启动测试失败: {result['error']}")
        
        return result
    
    def test_session_continuity(self):
        """测试会话连续性对响应时间的影响"""
        print("\n=== 会话连续性测试 ===")
        print("测试同一个会话中多次请求的响应时间变化")
        
        session_id = f"continuity_test_{int(time.time())}"
        query = "告诉我一些关于Python的有趣事实"
        
        response_times = []
        
        for i in range(10):
            print(f"  会话请求 {i+1}/10", end="")
            
            result = self.send_single_request(query, session_id)
            
            if result["success"]:
                response_times.append(result["response_time"])
                print(f" -> {result['response_time']:.2f}ms")
            else:
                print(f" -> 失败: {result['error']}")
        
        if response_times:
            print(f"\n会话连续性统计:")
            print(f"  第一次请求: {response_times[0]:.2f}ms")
            print(f"  最后一次请求: {response_times[-1]:.2f}ms")
            print(f"  平均响应时间: {statistics.mean(response_times):.2f}ms")
            
            # 检查响应时间趋势
            if len(response_times) > 1:
                trend = "上升" if response_times[-1] > response_times[0] else "下降"
                print(f"  响应时间趋势: {trend}")
        
        return response_times
    
    def generate_report(self, all_results):
        """生成测试报告"""
        print("\n" + "="*60)
        print("响应时间测试报告")
        print("="*60)
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"服务端点: {self.api_endpoint}")
        
        if 'sequential' in all_results:
            print("\n--- 单用户顺序请求测试结果 ---")
            sequential_results = all_results['sequential']
            
            # 按复杂度分组
            complexity_groups = {"低": [], "中": [], "高": []}
            
            for query_name, result in sequential_results.items():
                complexity = result["complexity"]
                complexity_groups[complexity].append(result["avg_time"])
            
            for complexity, times in complexity_groups.items():
                if times:
                    avg_time = statistics.mean(times)
                    print(f"{complexity}复杂度查询平均响应时间: {avg_time:.2f}ms")
        
        if 'cold_start' in all_results:
            print("\n--- 冷启动测试结果 ---")
            cold_start_result = all_results['cold_start']
            if cold_start_result["success"]:
                print(f"冷启动响应时间: {cold_start_result['response_time']:.2f}ms")
            else:
                print("冷启动测试失败")
        
        if 'continuity' in all_results:
            print("\n--- 会话连续性测试结果 ---")
            continuity_results = all_results['continuity']
            if continuity_results:
                print(f"会话内平均响应时间: {statistics.mean(continuity_results):.2f}ms")
                print(f"响应时间变化范围: {min(continuity_results):.2f}ms - {max(continuity_results):.2f}ms")
        
        print("\n" + "="*60)
        print("测试建议:")
        print("- 如果响应时间 > 100ms: 考虑进一步优化配置")
        print("- 如果冷启动时间明显偏高: 检查服务启动和初始化过程")
        print("- 如果会话内响应时间持续上升: 可能存在内存泄漏或状态累积")
        print("="*60)
    
    def run_all_tests(self):
        """运行所有测试"""
        print("开始响应时间测试...")
        
        # 检查服务健康状态
        if not self.check_service_health():
            print("❌ 服务未正常运行，请确保PE Server已启动")
            return
        
        print("✅ 服务运行正常")
        
        all_results = {}
        
        # 1. 冷启动测试
        all_results['cold_start'] = self.test_cold_start()
        
        # 2. 单用户顺序请求测试
        all_results['sequential'] = self.test_single_user_sequential()
        
        # 3. 会话连续性测试
        all_results['continuity'] = self.test_session_continuity()
        
        # 生成报告
        self.generate_report(all_results)
        
        return all_results

if __name__ == "__main__":
    # 检查命令行参数
    base_url = "http://127.0.0.1:25535"
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    
    print(f"PE Server响应时间测试")
    print(f"目标地址: {base_url}")
    print("="*60)
    
    tester = ResponseTimeTest(base_url)
    results = tester.run_all_tests()
    
    print("\n测试完成！")