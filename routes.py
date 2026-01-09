# routes.py
import json
import io
import threading
import time
import re
import secrets
from flask import Blueprint, render_template, request, Response, stream_with_context, jsonify, send_file, session

# 引入配置和工具
import config
from utils.word import MarkdownToDocx, TextReportParser
from utils.paperautowriter import PaperAutoWriter
from utils.state import task_manager
from utils.worker import background_worker
from utils.auth import check_auth, is_valid_key, VALID_KEYS, save_keys

# 创建蓝图
bp = Blueprint('main', __name__)

# ===================== 页面路由 =====================

@bp.route('/')
def index():
    return render_template('index.html')

@bp.route('/admin')
def admin_page(): 
    return render_template('admin.html')

# ===================== 鉴权路由 =====================

@bp.route('/verify_login', methods=['POST'])
def verify_login():
    key = request.json.get('key', '').strip()
    if is_valid_key(key):
        return jsonify({"status": "success", "msg": "登录成功"})
    else:
        return jsonify({"status": "fail", "msg": "无效的卡密"}), 401

@bp.route('/api/admin/login', methods=['POST'])
def admin_login():
    if request.json.get('username') == config.ADMIN_USERNAME and request.json.get('password') == config.ADMIN_PASSWORD:
        session['is_admin'] = True
        return jsonify({"status": "success"})
    return jsonify({"status": "fail"}), 401

@bp.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('is_admin', None)
    return jsonify({"status": "success"})

@bp.route('/api/admin/keys', methods=['GET', 'POST', 'DELETE'])
def manage_keys():
    if not session.get('is_admin'): return "Unauthorized", 401
    if request.method == 'GET': 
        return jsonify({"keys": list(VALID_KEYS)})
    if request.method == 'DELETE':
        key = request.json.get('key')
        if key in VALID_KEYS: 
            VALID_KEYS.remove(key)
            save_keys()
        return jsonify({"status": "success"})
    if request.method == 'POST':
        custom = request.json.get('key', '').strip()
        new_key = custom if custom else f"key_{secrets.token_hex(4)}"
        if new_key in VALID_KEYS: return jsonify({"status": "fail", "msg": "Exists"}), 400
        VALID_KEYS.add(new_key)
        save_keys()
        return jsonify({"status": "success", "key": new_key})

# ===================== 业务功能路由 =====================

@bp.route('/control', methods=['POST'])
def control_task():
    if not check_auth(): return jsonify({"error": "无效的卡密"}), 401
    
    user_id = request.headers.get('X-User-ID')
    data = request.json
    task_id = data.get('task_id')
    action = data.get('action')
    
    if not task_id: return jsonify({"error": "Missing task_id"}), 400

    if action == 'pause': task_manager.set_status(user_id, task_id, 'paused')
    elif action == 'resume': task_manager.set_status(user_id, task_id, 'running')
    elif action == 'stop': task_manager.set_status(user_id, task_id, 'stopped')
    
    return jsonify({"status": "success"})

@bp.route('/rewrite_section', methods=['POST'])
def rewrite_section():
    if not check_auth(): return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    title = data.get('title')
    section_title = data.get('section_title')
    instruction = data.get('instruction')
    context = data.get('context', '') 
    custom_data = data.get('custom_data', '')
    original_content = data.get('original_content', '')
    
    if not section_title: return jsonify({"error": "No section title"}), 400

    writer = PaperAutoWriter(config.API_KEY, config.BASE_URL, config.MODEL_NAME)
    
    try:
        new_content = writer.rewrite_chapter(title, section_title, instruction, context, custom_data, original_content)
        # 简单清洗
        clean_pattern = r'^#+\s*' + re.escape(section_title) + r'.*\n'
        new_content = re.sub(clean_pattern, '', new_content, flags=re.IGNORECASE|re.MULTILINE).strip()
        
        return jsonify({"status": "success", "content": new_content})
    except Exception as e:
        print(f"Rewrite error: {e}")
        return jsonify({"status": "error", "msg": str(e)}), 500

@bp.route('/export_docx', methods=['POST'])
def export_docx():
    if not check_auth(): return jsonify({"error": "无效的卡密"}), 401
    data = request.json
    try:
        file_stream = MarkdownToDocx.convert(data.get('content', ''))
        return send_file(file_stream, as_attachment=True, download_name='thesis.docx')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/generate', methods=['POST'])
def generate_start():
    if not check_auth(): return jsonify({"error": "Unauthorized"}), 401
    user_id = request.headers.get('X-User-ID')
    
    raw_chapters = request.form.get('chapter_data')
    title = request.form.get('title')
    ref_domestic = request.form.get('ref_domestic', '')
    ref_foreign = request.form.get('ref_foreign', '')
    text_custom_data = request.form.get('custom_data', '')
    extra_instructions = request.form.get('extra_instructions', '')
    task_id = request.form.get('task_id')
    initial_context = request.form.get('initial_context', '')
    
    uploaded_files = request.files.getlist('data_files')
    raw_files_data = []
    
    if uploaded_files:
        for file in uploaded_files:
            if file.filename:
                file_content = io.BytesIO(file.read())
                raw_files_data.append({
                    'name': file.filename, 
                    'content': file_content
                })

    task_manager.start_task(user_id, task_id)
    writer = PaperAutoWriter(config.API_KEY, config.BASE_URL, config.MODEL_NAME)
    
    def check_status_func(uid=user_id, tid=task_id):
        return task_manager.get_status(uid, tid)

    t = threading.Thread(
        target=background_worker,
        args=(writer, task_id, title, json.loads(raw_chapters), ref_domestic, ref_foreign, text_custom_data, raw_files_data, check_status_func, initial_context, user_id, extra_instructions)
    )
    t.daemon = True 
    t.start()

    return jsonify({"status": "success", "msg": "Task started in background"})

@bp.route('/stream_progress')
def stream_progress():
    if not check_auth(): return "Unauthorized", 401
    
    user_id = request.headers.get('X-User-ID')
    task_id = request.args.get('task_id')
    try: last_event_index = int(request.args.get('last_index', 0))
    except: last_event_index = 0

    def event_stream():
        current_idx = last_event_index
        while True:
            events, status = task_manager.get_events_from(user_id, task_id, current_idx)
            
            if events:
                for event in events:
                    event_str = str(event)
                    if not event_str.endswith('\n\n'):
                        event_str += '\n\n'
                    yield event_str
                    current_idx += 1
            else:
                if status in ['stopped', 'completed']:
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    break
                yield ": keep-alive\n\n"
                time.sleep(0.3)

    response = Response(stream_with_context(event_stream()), content_type='text/event-stream')
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Cache-Control'] = 'no-cache'
    return response

@bp.route('/api/smart_distribute', methods=['POST'])
def smart_distribute():
    if not check_auth(): return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    try:
        total_words = int(data.get('total_words', 5000))
        leaf_titles = data.get('leaf_titles', [])
        
        if not leaf_titles:
            return jsonify({"status": "error", "msg": "大纲列表为空"}), 400

        writer = PaperAutoWriter(config.API_KEY, config.BASE_URL, config.MODEL_NAME)
        distribution_map = writer.plan_word_count(total_words, leaf_titles)
        return jsonify({"status": "success", "distribution": distribution_map})
        
    except Exception as e:
        print(f"Distribute API Error: {e}")
        return jsonify({"status": "error", "msg": f"服务器内部错误: {str(e)}"}), 500
    
@bp.route('/api/parse_opening_report_text', methods=['POST'])
def parse_opening_report_text():
    if not check_auth(): return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    raw_text = data.get('text', '')
    
    if not raw_text or len(raw_text) < 10:
        return jsonify({"status": "error", "msg": "内容过短，请粘贴完整的开题报告"}), 400

    try:
        parsed_data = TextReportParser.parse(raw_text)
        return jsonify({"status": "success", "data": parsed_data})
    except Exception as e:
        print(f"Text Parse Error: {e}")
        return jsonify({"status": "error", "msg": str(e)}), 500