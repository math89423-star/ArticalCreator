
import json
import matplotlib
from flask import Flask, render_template, request, Response, stream_with_context, jsonify, send_file
from utils.word import MarkdownToDocx
from utils.prompts import PaperAutoWriter, TASK_STATES



# 设置后端为 Agg，确保在无显示器的服务器环境下也能运行
matplotlib.use('Agg') 
app = Flask(__name__)

# ==============================================================================
# 配置区域
# ==============================================================================
API_KEY = "sk-VuSl3xg7XTQUbWzs4QCeinJk70H4rhFUtrLdZlBC6hvjvs1t" # 替换 Key
BASE_URL = "https://tb.api.mkeai.com/v1"
MODEL_NAME = "deepseek-v3.2" 



# Routes
@app.route('/')
def index(): return render_template('index.html')

@app.route('/control', methods=['POST'])
def control_task():
    data = request.json
    TASK_STATES[data['task_id']] = 'paused' if data['action']=='pause' else ('running' if data['action']=='resume' else 'stopped')
    return jsonify({"status": "success"})

@app.route('/export_docx', methods=['POST'])
def export_docx():
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
    raw_chapters = request.form.get('chapter_data')
    title = request.form.get('title')
    references = request.form.get('references')
    task_id = request.form.get('task_id')
    TASK_STATES[task_id] = "running"
    return Response(stream_with_context(PaperAutoWriter(API_KEY, BASE_URL, MODEL_NAME).generate_stream(task_id, title, json.loads(raw_chapters), references)), content_type='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, host="192.168.0.35", port=5000, threaded=True)