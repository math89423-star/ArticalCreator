import json
import os
import secrets
import matplotlib
import docx          # [新增] 处理docx
import pandas as pd  # [新增] 处理表格
import pypdf         # [新增] 处理PDF
# 设置后端为 Agg，确保在无显示器的服务器环境下也能运行
matplotlib.use('Agg') 
from flask import Flask, render_template, request, Response, stream_with_context, jsonify, send_file, session, redirect, url_for
from utils.word import MarkdownToDocx
from utils.prompts import PaperAutoWriter
import threading
from collections import defaultdict

app = Flask(__name__)
app.secret_key = "super_secret_key_for_session" # 用于管理员登录Session

# ==============================================================================
# 配置区域
# ==============================================================================
API_KEY = "sk-VuSl3xg7XTQUbWzs4QCeinJk70H4rhFUtrLdZlBC6hvjvs1t" 
BASE_URL = "https://tb.api.mkeai.com/v1"
MODEL_NAME = "deepseek-v3.2" 

# 管理员账号配置 (建议生产环境使用更安全的方式存储)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

# 卡密存储文件
KEYS_FILE = "valid_keys.json"

# ==============================================================================
# 数据持久化与鉴权逻辑
# ==============================================================================
def load_keys():
    if not os.path.exists(KEYS_FILE):
        return []
    try:
        with open(KEYS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []

def save_keys(keys):
    with open(KEYS_FILE, 'w', encoding='utf-8') as f:
        json.dump(keys, f)

# 内存中缓存有效卡密，减少IO
VALID_KEYS = set(load_keys())

def is_valid_key(key):
    return key in VALID_KEYS

# --- 任务管理器 (线程安全 + 多用户隔离) ---
class TaskManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._user_tasks = defaultdict(dict)

    def set_status(self, user_id, task_id, status):
        with self._lock:
            if task_id not in self._user_tasks[user_id]:
                self._user_tasks[user_id][task_id] = {}
            self._user_tasks[user_id][task_id]['status'] = status

    def get_status(self, user_id, task_id):
        with self._lock:
            return self._user_tasks[user_id].get(task_id, {}).get('status', 'stopped')

task_manager = TaskManager()


def extract_file_content(file_storage) -> str:
    filename = file_storage.filename.lower()
    content = ""
    
    try:
        # 1. Excel/CSV
        if filename.endswith('.csv'):
            df = pd.read_csv(file_storage)
            content = f"\n【文件 {filename} 数据(前50行)】:\n" + df.head(50).to_markdown(index=False)
        
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file_storage)
            content = f"\n【文件 {filename} 数据(前50行)】:\n" + df.head(50).to_markdown(index=False)
            
        # 2. TXT
        elif filename.endswith('.txt'):
            text = file_storage.read().decode('utf-8', errors='ignore')
            content = f"\n【文件 {filename} 内容】:\n{text[:3000]}"
            
        # 3. PDF (忽略图片，只提文字)
        elif filename.endswith('.pdf'):
            reader = pypdf.PdfReader(file_storage)
            text = ""
            # 限制页数，防止过长
            for i, page in enumerate(reader.pages[:10]): 
                page_text = page.extract_text()
                if page_text: text += page_text + "\n"
            content = f"\n【文件 {filename} 内容提取(前10页)】:\n{text}"

        # 4. [新增] DOCX (忽略图片，只提文字)
        elif filename.endswith('.docx'):
            doc = docx.Document(file_storage)
            text = ""
            # 提取段落文本
            for para in doc.paragraphs:
                if para.text.strip():
                    text += para.text + "\n"
            # 提取表格文本 (可选)
            for table in doc.tables:
                for row in table.rows:
                    row_text = [cell.text.strip() for cell in row.cells]
                    text += " | ".join(row_text) + "\n"
            
            content = f"\n【文件 {filename} 内容提取】:\n{text[:5000]}" # 同样做个长度限制

        else:
            content = f"\n【文件 {filename}】: 不支持的文件格式。"
            
    except Exception as e:
        print(f"解析文件 {filename} 失败: {e}")
        content = f"\n【文件 {filename}】: 解析失败 - {str(e)}"
        
    return content


# ==============================================================================
# 路由逻辑
# ==============================================================================

@app.route('/')
def index():
    return render_template('index.html')

# --- 1. 用户鉴权接口 ---
@app.route('/verify_login', methods=['POST'])
def verify_login():
    key = request.json.get('key', '').strip()
    if is_valid_key(key):
        return jsonify({"status": "success", "msg": "登录成功"})
    else:
        return jsonify({"status": "fail", "msg": "无效的卡密，请联系管理员获取"}), 401

# --- 2. 管理员相关路由 ---
@app.route('/admin')
def admin_page():
    # if not session.get('is_admin'):
    #     return render_template('admin_login.html') # 需要新建这个简单页面或复用逻辑
    return render_template('admin.html')

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data.get('username') == ADMIN_USERNAME and data.get('password') == ADMIN_PASSWORD:
        session['is_admin'] = True
        return jsonify({"status": "success"})
    return jsonify({"status": "fail", "msg": "账号或密码错误"}), 401

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('is_admin', None)
    return jsonify({"status": "success"})

@app.route('/api/admin/keys', methods=['GET'])
def get_keys():
    if not session.get('is_admin'): return "Unauthorized", 401
    # 将集合转为列表返回
    return jsonify({"keys": list(VALID_KEYS)})

@app.route('/api/admin/keys', methods=['POST'])
def add_key():
    if not session.get('is_admin'): return "Unauthorized", 401
    # 1. 获取前端传来的自定义卡密
    data = request.json or {}
    custom_key = data.get('key', '').strip()
    new_key = ""
    # 2. 判断逻辑
    if custom_key:
        # 如果管理员输入了卡密，先检查是否已存在
        if custom_key in VALID_KEYS:
            return jsonify({"status": "fail", "msg": f"卡密 '{custom_key}' 已存在，请勿重复添加"}), 400
        new_key = custom_key
    else:
        # 如果管理员留空，则自动生成随机卡密 (保留原有逻辑作为备用)
        new_key = "key_" + secrets.token_hex(4)
        # 极小概率重复检查
        if new_key in VALID_KEYS:
             new_key = "key_" + secrets.token_hex(4)
    # 3. 保存
    VALID_KEYS.add(new_key)
    save_keys(list(VALID_KEYS))
    return jsonify({"status": "success", "key": new_key})

@app.route('/api/admin/keys', methods=['DELETE'])
def delete_key():
    if not session.get('is_admin'): return "Unauthorized", 401
    key_to_delete = request.json.get('key')
    if key_to_delete in VALID_KEYS:
        VALID_KEYS.remove(key_to_delete)
        save_keys(list(VALID_KEYS))
    return jsonify({"status": "success"})

# --- 3. 业务功能路由 (增加鉴权拦截) ---

def check_auth():
    """辅助函数：检查请求头中的卡密是否有效"""
    user_id = request.headers.get('X-User-ID')
    if not user_id or user_id not in VALID_KEYS:
        return False
    return True

@app.route('/control', methods=['POST'])
def control_task():
    if not check_auth(): return jsonify({"error": "无效的卡密"}), 401
    
    user_id = request.headers.get('X-User-ID')
    data = request.json
    task_id = data.get('task_id')
    action = data.get('action')
    
    if action == 'pause': 
        task_manager.set_status(user_id, task_id, 'paused')
    elif action == 'resume': 
        task_manager.set_status(user_id, task_id, 'running')
    elif action == 'stop': 
        task_manager.set_status(user_id, task_id, 'stopped')
        
    return jsonify({"status": "success"})

@app.route('/export_docx', methods=['POST'])
def export_docx():
    # 导出可适度放宽，或者也加上鉴权
    if not check_auth(): return jsonify({"error": "无效的卡密"}), 401
    
    data = request.json
    try:
        file_stream = MarkdownToDocx.convert(data.get('content', ''))
        return send_file(file_stream, as_attachment=True, download_name='thesis.docx')
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/generate', methods=['POST'])
def generate():
    # 【核心安全拦截】
    if not check_auth(): return "Unauthorized: Invalid Key", 401

    user_id = request.headers.get('X-User-ID')
    raw_chapters = request.form.get('chapter_data')
    title = request.form.get('title')
    references = request.form.get('references')
    custom_data = request.form.get('custom_data', '')
    task_id = request.form.get('task_id')
    initial_context = request.form.get('initial_context', '') 
    
    task_manager.set_status(user_id, task_id, 'running')
    
    writer = PaperAutoWriter(API_KEY, BASE_URL, MODEL_NAME)
    
    def check_status_func():
        return task_manager.get_status(user_id, task_id)

    return Response(
        stream_with_context(
            writer.generate_stream(
                task_id, 
                title, 
                json.loads(raw_chapters), 
                references, 
                custom_data, 
                check_status_func,
                initial_context 
            )
        ), 
        content_type='text/event-stream'
    )

if __name__ == '__main__':
    # 初始化一个默认 key 方便调试，如果文件不存在
    if not os.path.exists(KEYS_FILE):
        VALID_KEYS.add("test_vip_888")
        save_keys(list(VALID_KEYS))
        print("初始化默认卡密: test_vip_888")
        
    app.run(debug=True, host="0.0.0.0", port=8001, threaded=True)