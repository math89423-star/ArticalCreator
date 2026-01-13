# app.py

import matplotlib
# 设置后端为 Agg，确保在无显示器的服务器环境下也能运行
matplotlib.use('Agg') 

from flask import Flask
from waitress import serve
import config
from routes import bp as main_bp
from utils.auth import load_keys # 确保启动时加载 Key

app = Flask(__name__)
app.secret_key = config.SECRET_KEY 

# 注册蓝图 (路由)
app.register_blueprint(main_bp)

if __name__ == '__main__':
    # 确保 Key 已加载或初始化
    load_keys()
    
    print("🚀 服务器正在启动...")
    print("⚠️  请访问 http://223.109.143.195:8001 (或服务器IP)")
    print("✅ 已启用 Waitress 高并发模式，支持多任务同时运行")
    
    # ✅ 使用 Waitress 启动
    serve(app, host="0.0.0.0", port=8001, threads=100, connection_limit=200, channel_timeout=300)