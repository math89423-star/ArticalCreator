import time
import json
import re
import math
from typing import List, Dict, Generator, Tuple
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
# 工具类：文本清洗
# ==============================================================================
class TextCleaner:
    @staticmethod
    def convert_cn_numbers(text: str) -> str:
        """
        1. 全角数字转半角
        2. 中文数字转阿拉伯数字
        """
        # --- 1. 全角转半角 ---
        full_width_map = {
            '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
            '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
            '％': '%', '．': '.', '：': ':', '，': ',' 
        }
        for full, half in full_width_map.items():
            if full in ['％', '．', '０', '１', '２', '３', '４', '５', '６', '７', '８', '９']:
                text = text.replace(full, half)

        # --- 2. 中文年份转换 ---
        def year_repl(match):
            cn_year = match.group(1)
            mapping = {'零': '0', '一': '1', '二': '2', '三': '3', '四': '4', 
                       '五': '5', '六': '6', '七': '7', '八': '8', '九': '9'}
            return "".join([mapping.get(c, c) for c in cn_year]) + "年"
        
        text = re.sub(r'([零一二三四五六七八九]{4})年', year_repl, text)

        # --- 3. 清洗 ---
        text = text.replace("百分之", "").replace("％", "%") 
        text = text.replace("二0", "20").replace("二1", "21")
        
        return text

# ==============================================================================
# 1. 引用管理器 (智能分发 + 严格顺序)
# ==============================================================================
class ReferenceManager:
    def __init__(self, raw_references: str):
        raw_lines = [r.strip() for r in raw_references.split('\n') if r.strip()]
        self.all_refs = []
        clean_pattern = re.compile(r'^(\[\d+\]|\d+\.|（\d+）|\(\d+\))\s*')
        for line in raw_lines:
            cleaned_line = clean_pattern.sub('', line)
            self.all_refs.append(cleaned_line)

    def is_chinese(self, text: str) -> bool:
        return bool(re.search(r'[\u4e00-\u9fa5]', text))

    def distribute_references_smart(self, chapters: List[Dict]) -> Dict[int, List[Tuple[int, str]]]:
        if not self.all_refs: return {}
        
        # 1. 分类 (保持全局ID: 1-based)
        cn_refs = [ (i+1, r) for i, r in enumerate(self.all_refs) if self.is_chinese(r) ]
        en_refs = [ (i+1, r) for i, r in enumerate(self.all_refs) if not self.is_chinese(r) ]

        domestic_idxs = []
        foreign_idxs = []
        general_idxs = []
        last_content_idx = -1

        for i, chapter in enumerate(chapters):
            if chapter.get('is_parent'): continue
            title = chapter['title']
            
            if "参考文献" not in title and "致谢" not in title and "摘要" not in title:
                 last_content_idx = i

            # 关键词匹配
            if any(k in title for k in ["现状", "综述", "Review", "Status"]):
                if "国内" in title or "我国" in title:
                    domestic_idxs.append(i)
                elif "国外" in title or "国际" in title:
                    foreign_idxs.append(i)
                else:
                    general_idxs.append(i)

        allocation = {} 

        def assign_chunks(refs_list, target_idxs):
            if not target_idxs: return refs_list
            if not refs_list: return []
            chunk_size = math.ceil(len(refs_list) / len(target_idxs))
            for k, idx in enumerate(target_idxs):
                start = k * chunk_size
                chunk = refs_list[start : start + chunk_size]
                if not chunk: continue
                if idx not in allocation: allocation[idx] = []
                allocation[idx].extend(chunk)
            return []

        rem_cn = assign_chunks(cn_refs, domestic_idxs)
        rem_en = assign_chunks(en_refs, foreign_idxs)
        
        # 剩余文献分配给通用综述章节
        rem_all = rem_cn + rem_en
        rem_all.sort(key=lambda x: x[0]) 
        rem_final = assign_chunks(rem_all, general_idxs)

        # 兜底：如果还有文献没分出去，给最后一个正文章节
        if rem_final:
             target = None
             if general_idxs: target = general_idxs[-1]
             elif domestic_idxs: target = domestic_idxs[-1]
             elif foreign_idxs: target = foreign_idxs[-1]
             elif last_content_idx != -1: target = last_content_idx
             
             if target is not None:
                 if target not in allocation: allocation[target] = []
                 allocation[target].extend(rem_final)

        # 排序
        for idx in allocation:
            allocation[idx].sort(key=lambda x: x[0])
            
        return allocation

    def set_current_chapter_refs(self, refs: List[Tuple[int, str]]):
        self.current_chapter_refs = list(refs) 

    def process_text_deterministic(self, text: str) -> str:
        """
        确定性替换：将 [REF] 标记按顺序替换为 [1], [2]...
        """
        result_text = ""
        parts = text.split('[REF]')
        
        for i, part in enumerate(parts):
            result_text += part
            if i < len(parts) - 1:
                if self.current_chapter_refs:
                    global_id, _ = self.current_chapter_refs.pop(0)
                    result_text += f"[{global_id}]"
                else:
                    pass
        
        # 兜底：如果AI漏加了 [REF]，强制追加剩余文献
        if self.current_chapter_refs:
            result_text += "\n\n"
            remaining_ids = []
            while self.current_chapter_refs:
                global_id, _ = self.current_chapter_refs.pop(0)
                remaining_ids.append(f"[{global_id}]")
            result_text += f"此外，相关研究还涵盖了多方面的探索{ ''.join(remaining_ids) }。"
            
        return result_text

    def generate_bibliography(self) -> str:
        if not self.all_refs: return ""
        res = "## 参考文献\n\n"
        for i, ref_content in enumerate(self.all_refs):
            res += f"[{i+1}] {ref_content}\n\n"
        return res

# ==============================================================================
# 2. 提示词生成 (核心：严格遵循您的写作要求)
# ==============================================================================
def get_academic_thesis_prompt(target_words: int, ref_content_list: List[str], current_chapter_title: str) -> str:
    
    # ------------------------------------------------------------------
    # 1. 章节专属逻辑 (Section Specific Logic)
    # ------------------------------------------------------------------
    section_rule = ""
    is_abstract = "摘要" in current_chapter_title or "Abstract" in current_chapter_title
    
    # A. 摘要
    if is_abstract:
        section_rule = f"""
**当前任务：撰写摘要与关键词**
**逻辑结构**:
1. **研究背景**: 简述背景（约50字）。
2. **方法创新**: 做了什么，用了什么方法（约100字）。
3. **关键发现**: 得到了什么数据或结论（约100字）。
4. **理论贡献**: 价值是什么（约50字）。

**输出格式**:
### 摘要
　　[中文摘要内容，350字左右]
**关键词**：[从题目提取3-5个名词，用分号隔开]

### Abstract
　　[English Abstract, strictly corresponding]
**Keywords**: [English Keywords]
"""

    # B. 背景与意义
    elif "背景" in current_chapter_title:
        section_rule = """
**当前任务：撰写研究背景**
**要求**:
1. **真实政策**: 必须结合近几年中国真实存在的国家政策、最新文件、重大相关事项。
2. **数据支撑**: 需要一点真实数据作为背景支撑。
3. **篇幅**: 350字左右，不泛泛而谈。
"""
    elif "意义" in current_chapter_title:
        section_rule = """
**当前任务：撰写研究意义**
**要求**:
1. **理论意义**: 严禁说“填补了空白”，必须说“**丰富了...理论框架**”或“**为...提供了实证补充**”。
2. **实际意义**: 解决具体行业或社会痛点。
3. **篇幅**: 350字左右。
"""

    # C. 国内外研究现状 (最复杂的引用逻辑)
    elif any(k in current_chapter_title for k in ["现状", "综述", "Review"]):
        # 构建特殊的引用指令
        if ref_content_list:
            first_ref = ref_content_list[0]
            other_refs_prompt = "、".join([f"参考文献ID_{i+1}" for i in range(len(ref_content_list)-1)]) if len(ref_content_list) > 1 else "无"
            
            section_rule = f"""
**当前任务：撰写研究现状 (总-分-总结构)**
**严格逻辑**:
1. **第一段 (导语)**: 简单概述标题内容，约80-100字，最后一句引出下方引用。
2. **第二段 (核心引用)**: 
   - **首条详述**: 必须对列表中的**第一条参考文献**进行详细阐述（约200字）。
   - **后续罗列**: 对剩余的参考文献进行顺序综述，格式为“谁谁谁(年份)提出了...[REF]”。
   - **本段总字数**: 不低于450字。
3. **第三段 (评述/启示)**: 总结这些文献给本研究带来的启示（约100字）。

**分配的文献**:
- **首条重点文献**: {first_ref}
- **后续文献**: {other_refs_prompt} (请按顺序使用 [REF] 标记)
"""
        else:
            section_rule = "**当前任务：撰写研究现状**\n请基于通用学术知识撰写，保持总分总结构。"

    # D. 文献述评
    elif "述评" in current_chapter_title:
        section_rule = """
**当前任务：撰写文献述评**
**要求**: 
1. **不引用**: 此部分不需要引用具体文献。
2. **内容**: 总结前文文献的不足，指出本研究的切入点（借鉴什么，丰富什么）。
3. **篇幅**: 一个段落，300字左右。
"""

    # E. 研究内容
    elif "研究内容" in current_chapter_title and "方法" not in current_chapter_title:
        section_rule = """
**当前任务：撰写研究内容**
**格式**: 分段式回答。
1. **导语**: “本研究主要研究...，具体内容如下：”
2. **分章节**: 
   - “第一部分，绪论。主要阐述...”
   - “第二部分，...。分析了...”
   - ...
**要求**: 核心章节解释约200字，详略得当。
"""

    # F. 研究方法
    elif "研究方法" in current_chapter_title:
        section_rule = """
**当前任务：撰写研究方法**
**格式**: 分点回答，必须标序号 (1. 2. 3.)。
**必选方法 (按需选择)**:
1. **文献研究法**: (如有参考文献则必选)
2. **数据分析法**: (如有数据分析则必选)
3. **实证研究法/案例分析法**: (根据题目判断)
**要求**: 结合论文主题解释为什么用这个方法。
"""

    # G. 通用正文
    else:
        section_rule = """
**当前任务：撰写正文分析**
1. **逻辑主导**: 核心是分析思路。
2. **深度论述**: 每一段都要有观点、有论据（数据或理论）、有结论。
3. **数据规范**: 必须使用阿拉伯数字。
"""

    # ------------------------------------------------------------------
    # 2. 引用指令 (Token Insertion)
    # ------------------------------------------------------------------
    ref_instruction = ""
    # 只有综述类章节才启用强引用模式，其他章节按需
    if ref_content_list and any(k in current_chapter_title for k in ["现状", "综述", "Review"]):
        ref_instruction = f"""
### **策略D: 引用执行 (Token Strategy)**
本章节必须引用分配的 {len(ref_content_list)} 条文献。
1.  **不要生成序号**: 不要写 [1] [2]。
2.  **插入标记**: 在提到文献观点时，插入 **`[REF]`**。
3.  **数量**: 必须插入 {len(ref_content_list)} 个 `[REF]` 标记。
4.  **关联**: 即使文献不相关，也要用“此外，也有研究指出...”强行关联，**自圆其说**。
"""
    else:
        ref_instruction = "### **策略D: 引用策略**\n本章节无需强制引用列表中的文献，如需引用数据请使用真实知识。"

    word_count_strategy = f"目标: **{target_words} 字**。" if not is_abstract else "字数目标仅适用于中文部分。"

    return f"""
# 角色
你现在扮演一位**严谨的学术导师**，辅助学生撰写毕业论文。
任务：严格遵循特定的写作模板，保证学术规范，**绝不夸大成果**。

### **策略A: 格式与排版**
1.  **段落缩进**: **所有段落开头必须包含两个全角空格（　　）**。
2.  **禁用列表**: 严禁使用 Markdown 列表，必须写成连贯段落（研究方法除外）。

### **策略B: 数据与谦抑性 (CRITICAL)**
1.  **数字**: 必须使用“半角阿拉伯数字” (2024, 15.8%)。
2.  **严禁夸大**: 
    -   **禁止**: “填补空白”、“国内首创”、“完美解决”。
    -   **必须用**: “丰富了...视角”、“提供了实证参考”、“优化了...”。

### **策略C: 章节专属逻辑 (最高优先级)**
{section_rule}

{ref_instruction}

### **策略E: 字数控制**
{word_count_strategy}

请开始写作。
"""

# ==============================================================================
# 3. Paper Writing Agent
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

    def _research_phase(self, topic: str) -> str:
        system_prompt = "你是一个严谨的数据分析师。请列出关于主题的真实数据、政策文件。使用半角阿拉伯数字。仅列出核心3条。"
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"检索关于'{topic}'的真实事实："}
                ],
                temperature=0.3,
                stream=False
            )
            return response.choices[0].message.content.strip()
        except:
            return ""

    def generate_stream(self, task_id: str, title: str, chapters: List[Dict], references_raw: str) -> Generator[str, None, None]:
        ref_manager = ReferenceManager(references_raw)
        
        yield f"data: {json.dumps({'type': 'log', 'msg': f'系统初始化... 文献库载入: {len(ref_manager.all_refs)} 条'})}\n\n"
        
        chapter_ref_map = ref_manager.distribute_references_smart(chapters)

        full_content = f"# {title}\n\n"
        context = "这是论文的开头。"
        total_chapters = len(chapters)
        
        for i, chapter in enumerate(chapters):
            while TASK_STATES.get(task_id) == "paused":
                time.sleep(1)
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            if TASK_STATES.get(task_id) == "stopped":
                yield f"data: {json.dumps({'type': 'log', 'msg': '任务已终止'})}\n\n"
                break

            sec_title = chapter['title']
            
            if chapter.get('is_parent', False):
                yield f"data: {json.dumps({'type': 'log', 'msg': f'>>> 章节标题: {sec_title}'})}\n\n"
                section_md = f"## {sec_title}\n\n" 
                full_content += section_md
                yield f"data: {json.dumps({'type': 'content', 'md': section_md})}\n\n"
                continue 

            target = int(chapter.get('words', 500))
            
            # 获取分配的文献
            assigned_refs = chapter_ref_map.get(i, [])
            ref_content_list = [r[1] for r in assigned_refs]
            ref_manager.set_current_chapter_refs(assigned_refs)
            
            log_msg = f"正在撰写 [{i+1}/{total_chapters}]: {sec_title}"
            if assigned_refs:
                log_msg += f" [需引用 {len(assigned_refs)} 篇]"
            yield f"data: {json.dumps({'type': 'log', 'msg': log_msg})}\n\n"
            
            # --- Phase 1: Research ---
            facts_context = ""
            if "摘要" not in sec_title and "结论" not in sec_title and "参考文献" not in sec_title:
                yield f"data: {json.dumps({'type': 'log', 'msg': f'   - 正在构建分析逻辑与事实核查...'})}\n\n"
                facts = self._research_phase(f"{title} - {sec_title}")
                if facts:
                    facts = TextCleaner.convert_cn_numbers(facts)
                    facts_context = f"\n【真实事实库】:\n{facts}"

            # --- Phase 2: Writing ---
            sys_prompt = get_academic_thesis_prompt(target, ref_content_list, sec_title)
            user_prompt = f"""
            论文题目：{title}
            当前章节：{sec_title}
            前文脉络：{context[-600:]}
            字数要求：{target}字
            {facts_context}
            """
            
            raw_content = self._call_llm(sys_prompt, user_prompt)
            
            # --- Post-Processing ---
            processed_content = ref_manager.process_text_deterministic(raw_content)
            processed_content = TextCleaner.convert_cn_numbers(processed_content)
            
            # 缩进处理
            lines = processed_content.split('\n')
            formatted_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('　　') and not line.startswith('#'):
                    line = '　　' + line 
                formatted_lines.append(line)
            final_content = '\n\n'.join(formatted_lines)

            # 扩写 (摘要除外)
            if "摘要" not in sec_title and len(final_content) < target * 0.6:
                yield f"data: {json.dumps({'type': 'log', 'msg': f'   - 字数不足，进行深度扩写...'})}\n\n"
                # 扩写时不增加引用，只增加分析
                expand_prompt = sys_prompt + "\n内容篇幅不足。请增加逻辑分析和理论推演，保持学术谦抑性。"
                added_raw = self._call_llm(expand_prompt, f"请扩写：\n{raw_content}")
                added_processed = TextCleaner.convert_cn_numbers(added_raw) # 扩写不处理引用ID，防止乱序
                
                added_lines = [ '　　'+l.strip() if l.strip() and not l.startswith('　　') else l for l in added_processed.split('\n') ]
                final_content += '\n\n' + '\n\n'.join(added_lines)

            section_md = f"## {sec_title}\n\n{final_content}\n\n"
            full_content += section_md
            context = final_content 
            
            yield f"data: {json.dumps({'type': 'content', 'md': section_md})}\n\n"
            time.sleep(0.5)

        if TASK_STATES.get(task_id) != "stopped":
            yield f"data: {json.dumps({'type': 'log', 'msg': '生成参考文献...'})}\n\n"
            bib_section = ref_manager.generate_bibliography()
            full_content += bib_section
            yield f"data: {json.dumps({'type': 'content', 'md': bib_section})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        if task_id in TASK_STATES: del TASK_STATES[task_id]

# Routes
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