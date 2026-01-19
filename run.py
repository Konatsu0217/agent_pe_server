import sys
import os
from pathlib import Path

# 将 code 目录添加到 sys.path，以便能够正确导入模块
current_dir = Path(__file__).resolve().parent
code_dir = current_dir / "code"
sys.path.append(str(code_dir))

if __name__ == "__main__":
    import uvicorn
    from code.config_manager import ConfigManager
    
    config = ConfigManager.get_config()
    
    # 切换到 code 目录运行，或者确保 uvicorn 能找到 app
    # 这里我们使用 "code.main:app"
    uvicorn.run(
        "code.main:app",
        host="0.0.0.0",
        port=config['port'],
        workers=config.get('workers', 1),
        reload=config.get('reload', True),
        log_level="error",
    )
