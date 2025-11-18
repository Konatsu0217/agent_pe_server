"""
独立的配置管理模块，解决循环导入问题
"""
import json
from pathlib import Path
from typing import Dict, Any


class ConfigManager:
    """配置管理器，避免循环导入"""
    _config: Dict[str, Any] = None

    @classmethod
    def load_config(cls, config_path='config.json'):
        """加载配置文件"""
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
                'pe_session_history_service_url': config_data['pe_settings'].get('session_history_service_url', ''),
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
                'pe_session_history_service_url': "http://localhost:8000/session/history",
            }
            print(f"使用默认配置: {cls._config}")

    @classmethod
    def get_config(cls):
        """获取配置"""
        if cls._config is None:
            cls.load_config()
        return cls._config