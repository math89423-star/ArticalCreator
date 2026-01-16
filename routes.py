# routes.py
import json
import io
import threading
import time
import re
import secrets
import pypandoc
import os
import tempfile
import base64  # 【新增】需要处理图片Base64
from flask import Blueprint, render_template, request, Response, stream_with_context, jsonify, send_file, session

# 引入配置和工具
import config
from utils.word import MarkdownToDocx, TextReportParser
from utils.paperautowriter import PaperAutoWriter
from utils.state import task_manager
from utils.worker import background_worker
from utils.auth import check_auth, is_valid_key, VALID_KEYS, save_keys

# 引入 python-docx 相关库
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.oxml.ns import qn
from docx.enum.text import WD_LINE_SPACING, WD_ALIGN_PARAGRAPH

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
    
    title = request.form.get('title')
    section_title = request.form.get('section_title')
    instruction = request.form.get('instruction')
    context = request.form.get('context', '') 
    custom_data = request.form.get('custom_data', '')
    original_content = request.form.get('original_content', '')
    
    if not section_title: return jsonify({"error": "No section title"}), 400

    uploaded_files = request.files.getlist('rewrite_files')
    raw_files_data = []
    
    if uploaded_files:
        for file in uploaded_files:
            if file.filename:
                file_content = io.BytesIO(file.read())
                raw_files_data.append({
                    'name': file.filename, 
                    'content': file_content
                })

    writer = PaperAutoWriter(config.API_KEY, config.BASE_URL, config.MODEL_NAME)
    
    try:
        new_content = writer.rewrite_chapter(
            title, 
            section_title, 
            instruction, 
            context, 
            custom_data, 
            original_content,
            files=raw_files_data 
        )
        
        clean_pattern = r'^#+\s*' + re.escape(section_title) + r'.*\n'
        new_content = re.sub(clean_pattern, '', new_content, flags=re.IGNORECASE|re.MULTILINE).strip()
        
        return jsonify({"status": "success", "content": new_content})
    except Exception as e:
        print(f"Rewrite error: {e}")
        return jsonify({"status": "error", "msg": str(e)}), 500

# ===================== Word 导出核心逻辑 =====================

def set_run_font(run, font_size_pt, is_bold=False, is_heading=False):
    """
    底层 XML 修改：强制设置中西文混合字体
    """
    run.font.size = Pt(font_size_pt)
    run.font.bold = is_bold
    
    # 【修复 2】强制关闭斜体 (防止标题莫名其妙变斜体)
    run.font.italic = False 
    
    # 1. 设置西文 (Times New Roman)
    run.font.name = 'Times New Roman'
    
    # 2. 设置颜色为黑色
    run.font.color.rgb = RGBColor(0, 0, 0)
    
    # 3. 强制操作 XML 设置东亚字体
    r = run._element
    rPr = r.get_or_add_rPr()
    
    fonts = rPr.get_or_add_rFonts()
    
    if is_heading:
        fonts.set(qn('w:eastAsia'), '黑体')
    else:
        fonts.set(qn('w:eastAsia'), '宋体')
        
    fonts.set(qn('w:ascii'), 'Times New Roman')
    fonts.set(qn('w:hAnsi'), 'Times New Roman')

def is_list_paragraph(paragraph):
    """
    检测段落是否是列表项
    """
    p = paragraph._element
    pPr = p.get_or_add_pPr()
    return pPr.find(qn('w:numPr')) is not None

def preprocess_images_for_pandoc(text, temp_dir):
    """
    【核心修复】
    扫描文本中的 HTML <img> 标签（含 Base64 数据），
    将其提取并保存为临时文件，
    然后将 HTML 替换为标准 Markdown 图片语法 ![](path)。
    
    只有这样，Pandoc 才能在导出时正确插入图片。
    """
    # 正则：匹配 <div...><img src="data:image/xxx;base64,DATA"...></div> 或 单独的 <img ...>
    # 捕获组: 1=扩展名, 2=Base64数据
    # 这个正则兼容了可能有 div 包裹也可能没有的情况
    img_pattern = re.compile(
        r'(?:<div[^>]*class=["\']plot-container["\'][^>]*>\s*)?' 
        r'<img[^>]*src=["\']data:image/(?P<ext>png|jpg|jpeg|gif);base64,(?P<data>[^"\']+)["\'][^>]*>'
        r'(?:\s*</div>)?', 
        re.IGNORECASE
    )

    def replace_func(match):
        ext = match.group('ext')
        b64_data = match.group('data')
        
        try:
            # 1. 解码图片
            img_bytes = base64.b64decode(b64_data)
            
            # 2. 生成临时文件名 (绝对路径)
            filename = f"img_{secrets.token_hex(8)}.{ext}"
            file_path = os.path.join(temp_dir, filename)
            
            # 3. 写入文件
            with open(file_path, 'wb') as f:
                f.write(img_bytes)
            
            # 4. 替换为 Pandoc 认得的 Markdown 图片语法
            # 使用绝对路径，确保 Pandoc 能找到
            # 前后加换行，确保独立成段
            return f'\n\n![]({file_path})\n\n'
            
        except Exception as e:
            print(f"Image extract error: {e}")
            return match.group(0) # 失败则保持原样

    return img_pattern.sub(replace_func, text)

@bp.route('/export_docx', methods=['POST'])
def export_docx():
    if not check_auth(): return jsonify({"error": "无效的卡密"}), 401
    data = request.json
    content = data.get('content', '')
    
    if not content:
        return jsonify({"error": "无内容可导出"}), 400

    # 创建临时目录用于存放提取的图片
    # 使用 TemporaryDirectory 上下文管理器，确保处理完后自动清理图片
    with tempfile.TemporaryDirectory() as temp_img_dir:
        try:
            # =========================================================
            # [Step 1] 图片预处理 (HTML Base64 -> Markdown Path)
            # =========================================================
            # 这一步必须在清洗空格之前做，或者之后做都行，但必须在 Pandoc 之前
            processed_content = preprocess_images_for_pandoc(content, temp_img_dir)

            # =========================================================
            # [Step 2] 数据清洗
            # =========================================================
            # 移除段首的手动缩进
            cleaned_content = re.sub(r'(?m)^[ \t\u3000]+', '', processed_content)
            # 确保公式前后有空行
            cleaned_content = re.sub(r'(\$\$)', r'\n\1\n', cleaned_content)

            # =========================================================
            # [Step 3] Pandoc 转换 (Markdown -> Docx)
            # =========================================================
            with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp:
                temp_filename = tmp.name
            
            ref_doc_path = os.path.join(os.path.dirname(__file__), 'reference.docx')
            extra_args = []
            if os.path.exists(ref_doc_path):
                extra_args.append(f'--reference-doc={ref_doc_path}')
            
            # 转换
            pypandoc.convert_text(
                cleaned_content, 
                'docx', 
                format='markdown', 
                outputfile=temp_filename,
                extra_args=extra_args
            )

            # =========================================================
            # [Step 4] Python-docx 深度精修
            # =========================================================
            doc = Document(temp_filename)

            FONT_SIZE_BODY = 12     
            FONT_SIZE_HEADING = 16  
            INDENT_SIZE = Pt(24)    

            # --- A. 修改默认样式 ---
            try:
                style = doc.styles['Normal']
                style.font.name = 'Times New Roman'
                style.font.size = Pt(FONT_SIZE_BODY)
                style._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
                style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
            except:
                pass 

            # --- B. 遍历所有段落 ---
            for paragraph in doc.paragraphs:
                
                # --- 情况 1: 标题 ---
                if paragraph.style.name.startswith('Heading'):
                    paragraph.paragraph_format.first_line_indent = 0 
                    paragraph.paragraph_format.line_spacing = 1.5    
                    paragraph.paragraph_format.space_before = Pt(12) 
                    paragraph.paragraph_format.space_after = Pt(12)  
                    
                    for run in paragraph.runs:
                        set_run_font(run, FONT_SIZE_HEADING, is_bold=True, is_heading=True)

                # --- 情况 2: 正文和其他 ---
                else:
                    # 如果段落里包含图片（Docx中图片通常是 InlineShape），我们不应该强制缩进
                    # 简单判断：如果段落有 InlineShapes，不缩进，且居中
                    if paragraph.runs and len(paragraph.runs) == 1 and not paragraph.text.strip():
                        # 这可能是个图片段落（Pandoc转换后的图片往往在这里）
                        # 我们保持其默认格式，或者居中
                         paragraph.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
                         paragraph.paragraph_format.first_line_indent = 0
                    
                    elif not paragraph.text.strip():
                        continue
                    else:
                        pf = paragraph.paragraph_format
                        pf.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
                        
                        if is_list_paragraph(paragraph):
                            pf.first_line_indent = 0 
                        else:
                            pf.first_line_indent = INDENT_SIZE
                            pf.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

                        for run in paragraph.runs:
                            if not run.text: 
                                continue
                            set_run_font(run, FONT_SIZE_BODY, is_bold=False, is_heading=False)

            # 保存
            output_filename = temp_filename + "_formatted.docx"
            doc.save(output_filename)
            
            return send_file(
                output_filename, 
                as_attachment=True, 
                download_name='thesis_formatted.docx'
            )
            
        except OSError:
            return jsonify({"error": "服务器未安装 Pandoc"}), 500
        except Exception as e:
            print(f"Export Error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": f"导出处理失败: {str(e)}"}), 500

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