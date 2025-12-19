import time
import json
import re
import math
from typing import List, Dict, Generator, Tuple
from flask import Flask, render_template, request, Response, stream_with_context, jsonify
from openai import OpenAI

app = Flask(__name__)

# ==============================================================================
# Configuration
# ==============================================================================
API_KEY = "sk-VuSl3xg7XTQUbWzs4QCeinJk70H4rhFUtrLdZlBC6hvjvs1t" # Replace with actual Key
BASE_URL = "https://tb.api.mkeai.com/v1"
MODEL_NAME = "deepseek-v3.1" 

TASK_STATES = {}

# ==============================================================================
# Utility: Text Cleaner (Enforce Arabic Numerals + Full-width to Half-width)
# ==============================================================================
class TextCleaner:
    @staticmethod
    def convert_cn_numbers(text: str) -> str:
        """
        1. Full-width numbers to half-width (Fix font weirdness)
        2. Chinese numbers to Arabic numerals
        """
        # --- 1. Full-width to Half-width ---
        full_width_map = {
            '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
            '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
            '％': '%', '．': '.', '：': ':', '，': ',' 
        }
        for full, half in full_width_map.items():
            if full in ['％', '．', '０', '１', '２', '３', '４', '５', '６', '７', '８', '９']:
                text = text.replace(full, half)

        # --- 2. Chinese Year Conversion (二零二x年 -> 202x年) ---
        def year_repl(match):
            cn_year = match.group(1)
            mapping = {'零': '0', '一': '1', '二': '2', '三': '3', '四': '4', 
                       '五': '5', '六': '6', '七': '7', '八': '8', '九': '9'}
            return "".join([mapping.get(c, c) for c in cn_year]) + "年"
        
        text = re.sub(r'([零一二三四五六七八九]{4})年', year_repl, text)

        # --- 3. Percentage & Common Error Cleaning ---
        text = text.replace("百分之", "").replace("％", "%") 
        text = text.replace("二0", "20").replace("二1", "21")
        
        return text

# ==============================================================================
# 1. Reference Manager (Smart Distribution + Strict Order)
# ==============================================================================
class ReferenceManager:
    def __init__(self, raw_references: str):
        raw_lines = [r.strip() for r in raw_references.split('\n') if r.strip()]
        self.all_refs = []
        # Clean existing numbering (e.g., [1], 1., (1)) to avoid double numbering
        clean_pattern = re.compile(r'^(\[\d+\]|\d+\.|（\d+）|\(\d+\))\s*')
        for line in raw_lines:
            cleaned_line = clean_pattern.sub('', line)
            self.all_refs.append(cleaned_line)

    def is_chinese(self, text: str) -> bool:
        return bool(re.search(r'[\u4e00-\u9fa5]', text))

    def distribute_references_smart(self, chapters: List[Dict]) -> Dict[int, str]:
        if not self.all_refs: return {}
        
        # 1. Classify References
        cn_refs = [ (i, r) for i, r in enumerate(self.all_refs) if self.is_chinese(r) ]
        en_refs = [ (i, r) for i, r in enumerate(self.all_refs) if not self.is_chinese(r) ]

        # 2. Classify Chapters
        domestic_idxs = []
        foreign_idxs = []
        general_idxs = []
        last_content_chapter_idx = -1 # Track last suitable chapter for leftovers

        for i, chapter in enumerate(chapters):
            if chapter.get('is_parent'): continue
            title = chapter['title']
            
            # Identify chapters suitable for citations
            if "参考文献" not in title and "致谢" not in title and "摘要" not in title:
                 last_content_chapter_idx = i

            if any(k in title for k in ["现状", "综述", "Review", "Status", "背景", "意义", "引言", "绪论"]):
                if "国内" in title or "我国" in title or "China" in title:
                    domestic_idxs.append(i)
                elif "国外" in title or "国际" in title or "Foreign" in title:
                    foreign_idxs.append(i)
                else:
                    general_idxs.append(i)

        allocation = {} 

        def assign_chunks(refs_list, target_idxs):
            if not target_idxs: return refs_list # Return leftovers
            if not refs_list: return []
            
            chunk_size = math.ceil(len(refs_list) / len(target_idxs))
            for k, idx in enumerate(target_idxs):
                start = k * chunk_size
                chunk = refs_list[start : start + chunk_size]
                if not chunk: continue
                
                if idx not in allocation: allocation[idx] = []
                allocation[idx].extend(chunk)
            return [] # All assigned

        # 3. Distribute logic
        # Domestic refs -> Domestic chapters
        rem_cn = assign_chunks(cn_refs, domestic_idxs)
        # Foreign refs -> Foreign chapters
        rem_en = assign_chunks(en_refs, foreign_idxs)
        
        # Combine leftovers + assign to General chapters
        rem_all = rem_cn + rem_en
        # Sort by original index to maintain relative order
        rem_all.sort(key=lambda x: x[0]) 
        
        rem_final = assign_chunks(rem_all, general_idxs)

        # 4. Fallback: Force leftovers into the LAST content chapter if still unassigned
        if rem_final:
             target = None
             if general_idxs: target = general_idxs[-1]
             elif domestic_idxs: target = domestic_idxs[-1]
             elif foreign_idxs: target = foreign_idxs[-1]
             elif last_content_chapter_idx != -1: target = last_content_chapter_idx
             
             if target is not None:
                 if target not in allocation: allocation[target] = []
                 allocation[target].extend(rem_final)

        # 5. Build Prompt Context strings
        result_map = {}
        for idx, ref_list in allocation.items():
            # Crucial: Sort by original ID to enforce sequential order within the chapter
            ref_list.sort(key=lambda x: x[0])
            context = ""
            for global_idx, content in ref_list:
                snippet = content[:100] + "..." if len(content) > 100 else content
                context += f"ID_{global_idx}: {snippet}\n"
            result_map[idx] = context
        return result_map

    def process_text(self, text: str) -> str:
        """Replace [REF:ID_x] with [x+1]"""
        pattern = re.compile(r'\[REF:ID_(\d+)\]')
        def replace_func(match):
            try:
                ref_id = int(match.group(1))
                if ref_id < 0 or ref_id >= len(self.all_refs): return ""
                return f"[{ref_id + 1}]" 
            except:
                return ""
        return pattern.sub(replace_func, text)

    def generate_bibliography(self) -> str:
        if not self.all_refs: return ""
        res = "## 参考文献\n\n"
        for i, ref_content in enumerate(self.all_refs):
            res += f"[{i+1}] {ref_content}\n\n"
        return res

# ==============================================================================
# 2. Prompt Generation (Strict Citation Logic Update)
# ==============================================================================
def get_academic_thesis_prompt(target_words: int, ref_context: str, current_chapter_title: str) -> str:
    
    # --- Citation Logic ---
    ref_instruction = ""
    if ref_context:
        ref_instruction = f"""
### **策略D: 绝对强制引用协议 (Absolute Mandatory Citation)**
本章节被分配了特定的参考文献任务。你必须遵守以下**铁律**：

1.  **全量引用**: 列表中提供的**每一条**参考文献（ID_x）都必须在正文中出现一次。**严禁遗漏任何一条**。
2.  **严格次序**: 必须按照 ID 的数字顺序引用（先引用 ID_x，再引用 ID_x+1）。**严禁乱序**。
3.  **单次引用**: 每一条参考文献只允许被引用**一次**。
4.  **强制关联 (Forced Relevance)**: 
    * 如果某条参考文献的内容与当前段落逻辑不契合，你必须使用**过渡性语言**强行建立联系，做到“自圆其说”。
    * *示例技巧*: "此外，虽针对不同领域，但[REF:ID_x]的研究方法也为本问题提供了侧面参考..." 或 "考虑到更广泛的视角，[REF:ID_x]提出的观点也值得注意..."
    * **不要因为觉得不相关就丢弃它！这是任务失败的表现。**

**本章必须使用的文献清单**:
{ref_context}

**输出格式**: 在句子末尾标记 `[REF:ID_x]`。
"""
    else:
        ref_instruction = "### **策略D: 内容专注**\n本章节无需插入参考文献引用。"

    # --- Chapter Logic ---
    section_rule = ""
    is_abstract = "摘要" in current_chapter_title or "Abstract" in current_chapter_title

    if is_abstract:
        section_rule = f"""
**当前任务：撰写中英文摘要 (Compulsory Dual Language)**
**重要指令**：必须同时输出中文摘要和对应的英文摘要。
**字数参考**：中文部分约 {target_words} 字，英文部分不计入字数限制。

**输出格式严格如下**：
### 摘要
　　[中文摘要内容，包含背景、目的、方法、结果、结论]
**关键词**：[3-5个中文关键词，分号隔开]

### Abstract
　　[English Abstract Content, strictly corresponding to the Chinese version]
**Keywords**: [English Keywords]
"""
    elif "背景" in current_chapter_title or "意义" in current_chapter_title:
        section_rule = """
**当前任务：撰写背景与意义**
**适度引用**: 仅在介绍大背景时，适度引用1-2个最具代表性的真实政策文件作为切入点。
**核心要求**: 重点阐述研究的现实紧迫性、社会痛点。**切记使用中性语言，不要夸大研究的颠覆性**。
"""
    elif "现状" in current_chapter_title or "综述" in current_chapter_title:
        section_rule = "**当前任务：撰写文献综述**\n结构：总-分-总。必须把分配的参考文献全部用完。"
    else:
        section_rule = """
**当前任务：撰写正文分析**
1. **逻辑主导**: 核心是你的分析思路。
2. **克制引用**: 仅在需要关键数据支撑时引用，严禁像写政府工作报告一样罗列文件。
3. **深度论述**: 对现象背后的原因、机制进行剖析。
"""

    word_count_strategy = f"目标: **{target_words} 字**。" if not is_abstract else "字数目标仅适用于中文部分，英文部分请完整翻译。"

    return f"""
# 角色
你现在扮演一位**严谨的学术导师**，正在辅助一名**普通研究生**撰写学位论文。
任务：撰写逻辑缜密、符合学术规范、且**绝不夸大成果**的论文内容。

### **策略A: 格式与排版**
1.  **段落缩进**: **所有段落的开头必须包含两个全角空格（　　）**。
2.  **禁用列表**: 严禁使用 Markdown 列表。

### **策略B: 数据规范 (半角数字)**
1.  **数字格式**: **必须使用“半角阿拉伯数字”** (2024, 15.8%)。严禁全角或中文数字。
2.  **数据真实性**: 引用真实存在的历史数据，严禁捏造。

### **策略C: 论述平衡与学术谦抑 (CRITICAL)**
1.  **自主分析**: 文章 70% 以上必须是基于逻辑推演的**原创性论述**。不要大段复制政策文件。
2.  **严禁夸大成果 (Modesty Protocol)**:
    -   **绝对禁词**: 严禁使用“**填补了国内空白**”、“**首次提出**”、“**完美解决**”、“**彻底根除**”、“**国际领先**”等绝对化、夸张的词汇。
    -   **推荐表述**: 请使用“**丰富了...的视角**”、“**为...提供了实证参考**”、“**对...进行了有益探索**”、“**在一定程度上优化了...**”、“**补充了...的研究维度**”。
    -   **定位**: 这是一个学生层面的研究，通常是对现有理论的应用或局部改进，而非颠覆性创新。请保持谦虚、客观的学术语调。

### **策略D: 章节专属逻辑**
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
        """Simulate Research Phase"""
        system_prompt = """
        你是一个严谨的数据分析师。你的任务是回忆和检索关于以下主题的**真实数据、政策文件和关键事实**。
        请列出你记忆中确认无误的：
        1. 具体年份的数据（如GDP、人口、发病率等）。
        2. 具体的政策文件全称。
        
        要求：
        - 必须使用半角阿拉伯数字（2023年）。
        - 仅列出最核心的 1-3 条关键事实，不要列太多。
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"请检索关于'{topic}'的最核心真实事实："}
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
            ref_context = chapter_ref_map.get(i, "")
            
            log_msg = f"正在撰写 [{i+1}/{total_chapters}]: {sec_title}"
            if ref_context:
                ref_count = ref_context.count("ID_")
                log_msg += f" [引用 {ref_count} 篇]"
            yield f"data: {json.dumps({'type': 'log', 'msg': log_msg})}\n\n"
            
            # --- Phase 1: Research ---
            facts_context = ""
            if "摘要" not in sec_title and "结论" not in sec_title and "参考文献" not in sec_title:
                yield f"data: {json.dumps({'type': 'log', 'msg': f'   - 正在构建分析逻辑与事实核查...'})}\n\n"
                facts = self._research_phase(f"{title} - {sec_title}")
                if facts:
                    facts = TextCleaner.convert_cn_numbers(facts)
                    facts_context = f"\n【参考真实事实库】:\n{facts}\n(仅作为数据支撑，请勿大段复制，请结合你的逻辑进行分析)"

            # --- Phase 2: Writing ---
            sys_prompt = get_academic_thesis_prompt(target, ref_context, sec_title)
            user_prompt = f"""
            论文题目：{title}
            当前章节：{sec_title}
            前文脉络：{context[-600:]}
            字数要求：{target}字
            {facts_context}
            """
            
            raw_content = self._call_llm(sys_prompt, user_prompt)
            
            # --- Post-Processing ---
            processed_content = ref_manager.process_text(raw_content)
            processed_content = TextCleaner.convert_cn_numbers(processed_content)
            
            lines = processed_content.split('\n')
            formatted_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('　　') and not line.startswith('#'):
                    line = '　　' + line 
                formatted_lines.append(line)
            final_content = '\n\n'.join(formatted_lines)

            # 4. Expansion Logic
            if "摘要" not in sec_title and len(final_content) < target * 0.6:
                yield f"data: {json.dumps({'type': 'log', 'msg': f'   - 深度分析不足，正在进行逻辑扩展...'})}\n\n"
                expand_prompt = sys_prompt + "\n内容篇幅不足。请增加你的个人分析、逻辑推演，严禁使用'填补空白'等夸大词汇。"
                added_raw = self._call_llm(expand_prompt, f"请基于逻辑进行深度扩写：\n{raw_content}")
                added_processed = ref_manager.process_text(added_raw)
                added_processed = TextCleaner.convert_cn_numbers(added_processed)
                
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