import json
import os
import secrets
import matplotlib
# [新增依赖库]
import pandas as pd  # 处理 Excel/CSV
import pypdf         # 处理 PDF
import docx          # 处理 Word .docx

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

# 管理员账号配置
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

# 内存中缓存有效卡密
VALID_KEYS = set(load_keys())

def is_valid_key(key):
    return key in VALID_KEYS

# --- 任务管理器 ---
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

# ==============================================================================
# [新增] 多格式文件内容提取工具
# ==============================================================================
def extract_file_content(file_storage) -> str:
    """
    根据文件后缀名，提取文件内容为纯文本字符串。
    支持: .csv, .xlsx, .xls, .txt, .pdf, .docx
    """
    filename = file_storage.filename.lower()
    content = ""
    
    try:
        # 1. Excel/CSV (转为 Markdown 表格)
        if filename.endswith('.csv'):
            # 读取 CSV
            try:
                df = pd.read_csv(file_storage)
            except UnicodeDecodeError:
                # 尝试 GBK 编码 (中文常见)
                file_storage.seek(0)
                df = pd.read_csv(file_storage, encoding='gbk')
            
            # 限制行数，防止 Token 爆炸 (取前 60 行)
            content = f"\n【文件 {filename} 数据预览(前60行)】:\n" + df.head(60).to_markdown(index=False)
        
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file_storage)
            content = f"\n【文件 {filename} 数据预览(前60行)】:\n" + df.head(60).to_markdown(index=False)
            
        # 2. TXT (纯文本)
        elif filename.endswith('.txt'):
            content = f"\n【文件 {filename} 内容】:\n"
            try:
                text = file_storage.read().decode('utf-8')
            except:
                file_storage.seek(0)
                text = file_storage.read().decode('gbk', errors='ignore')
            content += text[:5000] # 限制长度
            
        # 3. PDF (提取文本，忽略图片)
        elif filename.endswith('.pdf'):
            reader = pypdf.PdfReader(file_storage)
            text = ""
            # 限制页数 (前 15 页)
            for i, page in enumerate(reader.pages[:15]): 
                page_text = page.extract_text()
                if page_text: 
                    text += f"[第{i+1}页] {page_text}\n"
            content = f"\n【文件 {filename} 内容提取】:\n{text}"

        # 4. DOCX (Word 文档)
        elif filename.endswith('.docx'):
            doc = docx.Document(file_storage)
            text = ""
            # 提取段落
            for para in doc.paragraphs:
                if para.text.strip():
                    text += para.text + "\n"
            # 提取表格 (简单转文本)
            for table in doc.tables:
                for row in table.rows:
                    row_text = [cell.text.strip() for cell in row.cells]
                    text += " | ".join(row_text) + "\n"
            
            content = f"\n【文件 {filename} 内容提取】:\n{text[:5000]}"

        else:
            content = f"\n【文件 {filename}】: 暂不支持该格式解析。"
            
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

@app.route('/verify_login', methods=['POST'])
def verify_login():
    key = request.json.get('key', '').strip()
    if is_valid_key(key):
        return jsonify({"status": "success", "msg": "登录成功"})
    else:
        return jsonify({"status": "fail", "msg": "无效的卡密，请联系管理员获取"}), 401

@app.route('/admin')
def admin_page():
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
    return jsonify({"keys": list(VALID_KEYS)})

@app.route('/api/admin/keys', methods=['POST'])
def add_key():
    if not session.get('is_admin'): return "Unauthorized", 401
    data = request.json or {}
    custom_key = data.get('key', '').strip()
    new_key = ""
    if custom_key:
        if custom_key in VALID_KEYS:
            return jsonify({"status": "fail", "msg": f"卡密 '{custom_key}' 已存在"}), 400
        new_key = custom_key
    else:
        new_key = "key_" + secrets.token_hex(4)
        if new_key in VALID_KEYS: new_key = "key_" + secrets.token_hex(4)
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

# --- 业务功能 ---

def check_auth():
    user_id = request.headers.get('X-User-ID')
    if not user_id or user_id not in VALID_KEYS: return False
    return True

@app.route('/control', methods=['POST'])
def control_task():
    if not check_auth(): return jsonify({"error": "无效的卡密"}), 401
    user_id = request.headers.get('X-User-ID')
    data = request.json
    task_id = data.get('task_id')
    action = data.get('action')
    if action == 'pause': task_manager.set_status(user_id, task_id, 'paused')
    elif action == 'resume': task_manager.set_status(user_id, task_id, 'running')
    elif action == 'stop': task_manager.set_status(user_id, task_id, 'stopped')
    return jsonify({"status": "success"})

@app.route('/export_docx', methods=['POST'])
def export_docx():
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
    # 1. 鉴权
    if not check_auth(): return "Unauthorized: Invalid Key", 401

    user_id = request.headers.get('X-User-ID')
    
    # 2. 获取表单文本数据
    raw_chapters = request.form.get('chapter_data')
    title = request.form.get('title')
    references = request.form.get('references')
    text_custom_data = request.form.get('custom_data', '') # 用户在文本框输入的
    task_id = request.form.get('task_id')
    initial_context = request.form.get('initial_context', '') 
    
    # 3. [核心修改] 处理上传的文件
    uploaded_files = request.files.getlist('data_files') # 获取文件列表
    file_extracted_text = ""
    
    if uploaded_files:
        for file in uploaded_files:
            if file.filename:
                # 调用解析函数
                file_extracted_text += extract_file_content(file) + "\n\n"
    
    # 4. 合并数据：文本框内容 + 文件解析内容
    final_custom_data = text_custom_data + "\n" + file_extracted_text
    
    # 5. 启动生成
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
                final_custom_data,  # 传入合并后的数据
                check_status_func,
                initial_context 
            )
        ), 
        content_type='text/event-stream'
    )

if __name__ == '__main__':
    if not os.path.exists(KEYS_FILE):
        VALID_KEYS.add("test_vip_888")
        save_keys(list(VALID_KEYS))
    app.run(debug=True, host="0.0.0.0", port=8001, threaded=True)