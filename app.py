import json
import matplotlib
matplotlib.use('Agg') 
from flask import Flask, render_template, request, Response, stream_with_context, jsonify, send_file
from utils.word import MarkdownToDocx
from utils.prompts import PaperAutoWriter
import threading
from collections import defaultdict

app = Flask(__name__)

API_KEY = "sk-VuSl3xg7XTQUbWzs4QCeinJk70H4rhFUtrLdZlBC6hvjvs1t" 
BASE_URL = "https://tb.api.mkeai.com/v1"
MODEL_NAME = "deepseek-v3.2" 

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/control', methods=['POST'])
def control_task():
    user_id = request.headers.get('X-User-ID')
    if not user_id: return jsonify({"error": "Unauthorized"}), 401
    
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
    # 导出接口可以放宽鉴权，只要内容有效即可
    data = request.json
    try:
        file_stream = MarkdownToDocx.convert(data.get('content', ''))
        return send_file(file_stream, as_attachment=True, download_name='thesis.docx')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/generate', methods=['POST'])
def generate():
    user_id = request.headers.get('X-User-ID')
    if not user_id: return "Unauthorized", 401

    raw_chapters = request.form.get('chapter_data')
    title = request.form.get('title')
    references = request.form.get('references')
    custom_data = request.form.get('custom_data', '')
    task_id = request.form.get('task_id')
    
    # 【新增】获取上下文
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
                initial_context  # 【传递参数】
            )
        ), 
        content_type='text/event-stream'
    )

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0", port=8001, threaded=True)