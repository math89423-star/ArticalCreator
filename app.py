import time
import json
import re
import uuid
from typing import List, Dict, Generator
from flask import Flask, render_template, request, Response, stream_with_context, jsonify
from openai import OpenAI

app = Flask(__name__)

# ==============================================================================
# 配置区域
# ==============================================================================
API_KEY = "sk-VuSl3xg7XTQUbWzs4QCeinJk70H4rhFUtrLdZlBC6hvjvs1t" # 替换 Key
BASE_URL = "https://tb.api.mkeai.com/v1"
MODEL_NAME = "deepseek-v3.1" 

TASK_STATES = {}

# ==============================================================================
# 1. 引用管理器 (静态锚定 + 原样输出)
# ==============================================================================
class ReferenceManager:
    def __init__(self, raw_references: str):
        # 1. 按行分割，去除空行
        lines = [r.strip() for r in raw_references.split('\n') if r.strip()]
        self.all_refs = []
        
        # 2. 清洗用户输入的序号 (防止 "[1] 张三" 变成 "[1] [1] 张三")
        clean_pattern = re.compile(r'^(\[\d+\]|\d+\.|（\d+）|\(\d+\))\s*')
        
        for line in lines:
            cleaned_line = clean_pattern.sub('', line) 
            self.all_refs.append(cleaned_line)

    def get_prompt_context(self) -> str:
        """生成给 AI 看的列表，带ID索引"""
        if not self.all_refs: return ""
        context = ""
        for i, ref in enumerate(self.all_refs):
            # 截取前80个字给AI识别，保留足够信息
            snippet = ref[:80] + "..." if len(ref) > 80 else ref
            context += f"ID_{i}: {snippet}\n"
        return context

    def process_text(self, text: str) -> str:
        """将 [REF:ID_x] 替换为 [x+1]"""
        pattern = re.compile(r'\[REF:ID_(\d+)\]')
        
        def replace_func(match):
            try:
                ref_id = int(match.group(1))
                if ref_id < 0 or ref_id >= len(self.all_refs): return "" 
                return f"[{ref_id + 1}]" # 静态映射：ID_0 -> [1]
            except:
                return ""
        return pattern.sub(replace_func, text)

    def generate_bibliography(self) -> str:
        """生成最终列表：严格按用户输入顺序"""
        if not self.all_refs: return ""
        res = "## 参考文献\n\n"
        for i, ref_content in enumerate(self.all_refs):
            res += f"[{i+1}] {ref_content}\n\n"
        return res

# ==============================================================================
# 2. 终极提示词生成函数 (融合版)
# ==============================================================================
def get_academic_thesis_prompt(target_words: int, ref_context: str, current_chapter_title: str) -> str:
    
    # --- 1. 引用逻辑判断 ---
    is_review_section = any(k in current_chapter_title for k in ["现状", "综述", "Review", "Status", "背景"])
    
    ref_instruction = ""
    if is_review_section and ref_context:
        ref_instruction = f"""
### **策略C: 严格引用协议 (Reference Protocol)**
本章节属于综述性质，**必须**引用参考文献。
**操作规则**:
1.  **严禁直接生成序号**：你不知道全局顺序，严禁生成 `[1]` 或 `[2]`。
2.  **必须使用占位符**：当你引用库中 `ID_x` 的文献时，请在正文中标注 `[REF:ID_x]`。
    - *示例*: 根据研究 `[REF:ID_0]`，... 而李四认为 `[REF:ID_5]`。
3.  **可用参考文献库**:
{ref_context}
"""
    else:
        ref_instruction = "### **策略C: 内容专注**\n本章节重点在于逻辑分析，**无需**强制插入参考文献引用，请专注于内容深度。"

    # --- 2. 章节专属指令 ---
    section_rule = ""
    if "摘要" in current_chapter_title:
        section_rule = """
**当前任务：撰写中英文摘要**
请严格按照以下格式输出：
### 摘要
[中文摘要，约350字。包含背景、目的、方法、结论]
**关键词**：[3-5个中文关键词，分号隔开]

### Abstract
[对应英文摘要，语法严谨]
**Keywords**: [对应英文关键词]
"""
    elif "背景" in current_chapter_title or "意义" in current_chapter_title:
        section_rule = "**当前任务：撰写背景与意义**\n必须结合中国近几年真实政策与社会现状。年份必须用阿拉伯数字（如2024年）。"
    elif "现状" in current_chapter_title or "综述" in current_chapter_title:
        section_rule = "**当前任务：撰写文献综述**\n结构：总-分-总。必须结合参考文献进行评述，引用格式为 `[REF:ID_x]`。"
    elif "方法" in current_chapter_title and "内容" not in current_chapter_title:
        section_rule = "**当前任务：撰写研究方法**\n分点回答。包含：文献研究法、数据分析法、实证分析法等。"
    else:
        section_rule = "**当前任务：撰写正文分析**\n论证深度：隐含“为什么”和“怎么证明”。逻辑链清晰。"

    # --- 3. 终极 Prompt 组合 ---
    return f"""
# 角色 (Identity)
你现在扮演XX专业内的**顶尖学术研究者**与**风格拟态专家（Style Mimicry Expert）**。
你的任务是：撰写符合严谨学术标准、数据规范、完全去AI痕迹的论文内容。

# 核心策略 (Core Strategies) - 必须严格遵守

### **策略A: 深度风格拟态与去AI化**
*(目标：通过增加解释性、词汇替换和句式重塑，消除机器味)*

1.  **动词短语扩展 (Verbose Elaboration)**:
    -   将简洁动词替换为带过程描述的短语。
    -   *示例*: “管理”→“开展...的管理工作”；“分析”→“对...进行深度剖析”；“验证”→“开展相关的验证工作”。
2.  **词汇清洗 (Vocabulary Cleansing)**:
    -   **绝对禁词**: 冒号(:)、首先、其次、最后、综上所述、此外、因此、从而、进而、旨在、基于此、意味着、扮演、至关重要、赋能、抓手、一系列。
    -   **强制替换**: “借助/利用”→“靠着/凭借”；“剖析”→“分析”；“本文”→“本研究”；“提升”→“让...得到提高”。
3.  **句式重塑 (Structure)**:
    -   **长度控制**: 强制打破机械节奏，句子控制在 20-25 字，长短句交替。
    -   **多样化**: 大量使用**倒装句**（“针对...问题，本研究...”）、**省略句**（删去不必要的主语“我们”）。
4.  **隐性衔接**:
    -   **严禁使用路标词**。使用语义的自然流动来承接上下文。把逗号多的短句融合成长句。

### **策略B: 数据与实证规范 (Data Protocol)**
1.  **阿拉伯数字强制 (Arabic Numerals Only)**:
    -   **所有年份、统计数据、百分比、比例必须使用阿拉伯数字**。
    -   *正确*: 2024年, 15.8%, 3000万, 1:5, 3.1倍。
    -   *错误*: 二零二四年, 百分之十五, 三千万, 三点一倍。
2.  **模拟数据规则**: 
    -   若需模拟数据，**严禁使用整数**（如100%），**严禁使用2和5的倍数**（如20%, 50%）。
    -   数据必须精确到小数点后两位（如 34.17%），且符合逻辑。

{section_rule}

{ref_instruction}

### **策略E: 输出规范**
1.  **字数控制**: 本部分目标 **{target_words} 字**。拒绝空洞拖沓。
2.  **格式**: 
    -   **不要输出标题**（摘要章节除外）。
    -   **全文严禁使用冒号（:）**，请用文字连接。
    -   直接输出正文，用自然段落区分。

请开始写作。
"""

# ==============================================================================
# 3. 写作智能体
# ==============================================================================
class PaperAutoWriter:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7, 
                stream=False
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"[Error: {str(e)}]"

    def generate_stream(self, task_id: str, title: str, chapters: List[Dict], references_raw: str) -> Generator[str, None, None]:
        # 初始化引用管理器 (静态锚定)
        ref_manager = ReferenceManager(references_raw)
        ref_context = ref_manager.get_prompt_context()

        yield f"data: {json.dumps({'type': 'log', 'msg': f'系统初始化完成。文献库载入: {len(ref_manager.all_refs)} 条'})}\n\n"
        
        full_content = f"# {title}\n\n"
        context = "这是论文的开头。"
        
        total_chapters = len(chapters)
        
        for i, chapter in enumerate(chapters):
            # --- 暂停/停止逻辑 ---
            while TASK_STATES.get(task_id) == "paused":
                time.sleep(1)
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            
            if TASK_STATES.get(task_id) == "stopped":
                yield f"data: {json.dumps({'type': 'log', 'msg': '任务已终止'})}\n\n"
                break

            sec_title = chapter['title']
            
            # --- 父级节点处理 (只生成标题) ---
            if chapter.get('is_parent', False):
                yield f"data: {json.dumps({'type': 'log', 'msg': f'>>> 创建章节标题: {sec_title}'})}\n\n"
                section_md = f"## {sec_title}\n\n" 
                full_content += section_md
                yield f"data: {json.dumps({'type': 'content', 'md': section_md})}\n\n"
                continue 

            # --- 叶子节点生成 ---
            target = int(chapter.get('words', 500))
            yield f"data: {json.dumps({'type': 'log', 'msg': f'正在撰写 [{i+1}/{total_chapters}]: {sec_title} (目标 {target}字)...'})}\n\n"
            
            # 生成 Prompt
            sys_prompt = get_academic_thesis_prompt(target, ref_context, sec_title)
            user_prompt = f"论文题目：{title}\n当前章节：{sec_title}\n前文脉络：{context[-600:]}\n字数要求：{target}字"
            
            # 调用 LLM
            raw_content = self._call_llm(sys_prompt, user_prompt)
            
            # 替换引用 [REF:ID_x] -> [x+1]
            final_content = ref_manager.process_text(raw_content)
            
            # 扩写逻辑 (摘要除外)
            if "摘要" not in sec_title and len(final_content) < target * 0.6:
                yield f"data: {json.dumps({'type': 'log', 'msg': f'   - 字数不足，进行扩写...'})}\n\n"
                expand_prompt = sys_prompt + "\n内容篇幅不足，请在保持‘阿拉伯数字’和‘去AI化’风格的前提下，增加实证分析，大幅扩充篇幅。"
                added_raw = self._call_llm(expand_prompt, f"请扩写此内容：\n{raw_content}")
                final_content = ref_manager.process_text(added_raw)

            section_md = f"## {sec_title}\n\n{final_content}\n\n"
            full_content += section_md
            context = final_content 
            
            yield f"data: {json.dumps({'type': 'content', 'md': section_md})}\n\n"
            time.sleep(0.5)

        if TASK_STATES.get(task_id) != "stopped":
            # --- 生成参考文献 (原样输出) ---
            yield f"data: {json.dumps({'type': 'log', 'msg': '生成参考文献...'})}\n\n"
            bib_section = ref_manager.generate_bibliography()
            full_content += bib_section
            yield f"data: {json.dumps({'type': 'content', 'md': bib_section})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        if task_id in TASK_STATES: del TASK_STATES[task_id]

# 路由部分
@app.route('/')
def index(): return render_template('index.html')

@app.route('/control', methods=['POST'])
def control_task():
    data = request.json
    task_id = data.get('task_id')
    action = data.get('action')
    if not task_id: return jsonify({"error": "No task ID"}), 400
    if action == 'pause': TASK_STATES[task_id] = "paused"
    elif action == 'resume': TASK_STATES[task_id] = "running"
    elif action == 'stop': TASK_STATES[task_id] = "stopped"
    return jsonify({"status": "success", "current_state": TASK_STATES.get(task_id)})

@app.route('/generate', methods=['POST'])
def generate():
    raw_chapters = request.form.get('chapter_data') 
    title = request.form.get('title')
    references = request.form.get('references')
    task_id = request.form.get('task_id')
    
    if not raw_chapters or not task_id: return "Error", 400
    
    TASK_STATES[task_id] = "running"
    chapters = json.loads(raw_chapters)
    agent = PaperAutoWriter(API_KEY, BASE_URL, MODEL_NAME)
    
    return Response(stream_with_context(agent.generate_stream(task_id, title, chapters, references)), 
                    content_type='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)