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
# 1. 引用管理器 (智能分发版)
# ==============================================================================
class ReferenceManager:
    def __init__(self, raw_references: str):
        # 1. 清洗输入，去除原有的序号 (1. [1] (1) 等)
        raw_lines = [r.strip() for r in raw_references.split('\n') if r.strip()]
        self.all_refs = []
        
        # 匹配开头的序号并去除
        clean_pattern = re.compile(r'^(\[\d+\]|\d+\.|（\d+）|\(\d+\))\s*')
        
        for line in raw_lines:
            cleaned_line = clean_pattern.sub('', line)
            self.all_refs.append(cleaned_line)

    def is_chinese(self, text: str) -> bool:
        """检测文本是否包含中文字符"""
        return bool(re.search(r'[\u4e00-\u9fa5]', text))

    def distribute_references_smart(self, chapters: List[Dict]) -> Dict[int, str]:
        """
        智能分配参考文献：
        逻辑：
        1. 将所有文献分为 [CN_List] 和 [EN_List]。
        2. 扫描章节，找到 [Domestic_Idxs] (国内), [Foreign_Idxs] (国外), [General_Idxs] (通用)。
        3. 将 CN_List 分给 Domestic，EN_List 分给 Foreign。
        4. 剩余的（或无法匹配的）分给 General。
        5. 保证所有文献都被分配出去。
        """
        if not self.all_refs: return {}

        # 1. 文献分类 (保存 (GlobalIndex, Content))
        cn_refs = [] 
        en_refs = []
        for i, ref in enumerate(self.all_refs):
            if self.is_chinese(ref):
                cn_refs.append((i, ref))
            else:
                en_refs.append((i, ref))

        # 2. 章节分类
        domestic_idxs = []
        foreign_idxs = []
        general_idxs = []

        for i, chapter in enumerate(chapters):
            if chapter.get('is_parent'): continue
            title = chapter['title']
            
            # 只有综述类章节才参与分配
            if any(k in title for k in ["现状", "综述", "Review", "Status", "背景"]):
                if "国内" in title or "我国" in title or "China" in title:
                    domestic_idxs.append(i)
                elif "国外" in title or "国际" in title or "Foreign" in title:
                    foreign_idxs.append(i)
                else:
                    general_idxs.append(i)

        # 3. 分配算法
        allocation = {} # {chapter_idx: [ (id, content), ... ]}

        def assign_chunks(refs_list, target_idxs):
            """将 ref 列表平均切分给 target_idxs"""
            if not target_idxs: return refs_list # 返回未分配的
            if not refs_list: return []
            
            chunk_size = math.ceil(len(refs_list) / len(target_idxs))
            for k, idx in enumerate(target_idxs):
                start = k * chunk_size
                end = start + chunk_size
                chunk = refs_list[start:end]
                if not chunk: continue
                
                if idx not in allocation: allocation[idx] = []
                allocation[idx].extend(chunk)
            return [] # 全部分配完毕

        # (A) 中文 -> 国内章节
        rem_cn = assign_chunks(cn_refs, domestic_idxs)
        # (B) 英文 -> 国外章节
        rem_en = assign_chunks(en_refs, foreign_idxs)
        
        # (C) 剩余的所有 -> 通用章节
        rem_all = rem_cn + rem_en
        # 按原始序号排序，保持美观
        rem_all.sort(key=lambda x: x[0])
        rem_final = assign_chunks(rem_all, general_idxs)

        # (D) 极端兜底：如果还有剩余（说明连通用章节都没有），强行塞给最后一个可用的综述章节
        if rem_final:
            # 找一个“垃圾桶”章节
            target = None
            if general_idxs: target = general_idxs[-1]
            elif domestic_idxs: target = domestic_idxs[-1]
            elif foreign_idxs: target = foreign_idxs[-1]
            
            if target is not None:
                if target not in allocation: allocation[target] = []
                allocation[target].extend(rem_final)

        # 4. 生成最终 Prompt Context
        result_map = {}
        for idx, ref_list in allocation.items():
            # 再次排序，确保同一章节内的引用顺序是 [1], [2] 而不是 [2], [1]
            ref_list.sort(key=lambda x: x[0])
            
            context = ""
            for global_idx, content in ref_list:
                snippet = content[:100] + "..." if len(content) > 100 else content
                # 关键：使用 GlobalIndex (ID_0, ID_1) 确保全局唯一
                context += f"ID_{global_idx}: {snippet}\n"
            result_map[idx] = context
            
        return result_map

    def process_text(self, text: str) -> str:
        """
        将 [REF:ID_x] 替换为 [x+1]
        """
        pattern = re.compile(r'\[REF:ID_(\d+)\]')
        def replace_func(match):
            try:
                ref_id = int(match.group(1))
                if ref_id < 0 or ref_id >= len(self.all_refs): return ""
                return f"[{ref_id + 1}]" # ID_0 -> [1]
            except:
                return ""
        return pattern.sub(replace_func, text)

    def generate_bibliography(self) -> str:
        """生成最终参考文献列表"""
        if not self.all_refs: return ""
        res = "## 参考文献\n\n"
        for i, ref_content in enumerate(self.all_refs):
            # 严格按照用户输入的顺序输出
            res += f"[{i+1}] {ref_content}\n\n"
        return res

# ==============================================================================
# 2. 提示词生成函数 (包含格式控制)
# ==============================================================================
def get_academic_thesis_prompt(target_words: int, ref_context: str, current_chapter_title: str) -> str:
    
    # --- 引用逻辑 ---
    ref_instruction = ""
    if ref_context:
        ref_instruction = f"""
### **策略D: 强制引用协议 (Mandatory Citation)**
本章节分配了特定的参考文献（根据章节主题智能分配），你**必须全部引用**，并且**按顺序引用**。
即便文献内容与当前语境关联不强，你也必须使用“过渡性语言”（如：*此外，也有学者研究了...*）将其强行融入，**做到自圆其说**。

**分配给本章的文献**:
{ref_context}

**引用操作**:
1.  **必须使用**列表中所有的 ID。
2.  **格式**: 在句子末尾标记 `[REF:ID_x]`。
3.  **禁止遗漏**: 列表里的文献一个都不能少。
"""
    else:
        ref_instruction = "### **策略D: 内容专注**\n本章节**无需**插入参考文献引用，请专注于逻辑分析。"

    # --- 章节专属逻辑 ---
    section_rule = ""
    if "摘要" in current_chapter_title:
        section_rule = """
**当前任务：撰写中英文摘要**
格式要求：
### 摘要
　　[中文摘要，350字左右]
**关键词**：[中文关键词]

### Abstract
　　[English Abstract]
**Keywords**: [English Keywords]
"""
    elif "背景" in current_chapter_title or "意义" in current_chapter_title:
        section_rule = "**当前任务：撰写背景与意义**\n结合真实政策。年份必须用阿拉伯数字（如2024年）。"
    elif "现状" in current_chapter_title or "综述" in current_chapter_title:
        section_rule = "**当前任务：撰写文献综述**\n结构：总-分-总。必须把分配的参考文献全部用完。"
    else:
        section_rule = "**当前任务：撰写正文**\n论证深度：为什么？怎么证明？\n句式：倒装句、强调句。"

    return f"""
# 角色
你现在扮演XX专业内的**顶尖学术研究者**。
任务：撰写严谨、高困惑度、**完全去AI痕迹**的内容。

### **策略A: 格式与排版 (Strict Formatting)**
1.  **段落缩进**: **所有段落的开头必须包含两个全角空格（　　）**。这是死命令。
2.  **分段原则**: 
    -   严禁“一段到底”。
    -   严禁Markdown列表（Bullet points）。
    -   每段约 200-300 字，逻辑清晰。
3.  **标题禁忌**: 不要输出章节标题，直接写正文内容。

### **策略B: 语言拟态**
1.  **词汇清洗**: 禁词(冒号,首先,其次,综上所述,赋能,抓手)。
2.  **句式重塑**: 句子20-25字。多用倒装句。
3.  **数字规范**: **必须使用阿拉伯数字** (2024年, 15.8%)。严禁中文数字。

### **策略C: 章节专属逻辑**
{section_rule}

{ref_instruction}

### **策略E: 字数控制**
目标: **{target_words} 字**。确保内容充实。

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
        ref_manager = ReferenceManager(references_raw)
        
        yield f"data: {json.dumps({'type': 'log', 'msg': f'系统初始化... 文献库载入: {len(ref_manager.all_refs)} 条'})}\n\n"
        
        # --- 1. 智能分配参考文献 ---
        # 这一步会根据章节标题（国内/国外）自动分配对应的文献
        chapter_ref_map = ref_manager.distribute_references_smart(chapters)

        full_content = f"# {title}\n\n"
        context = "这是论文的开头。"
        total_chapters = len(chapters)
        
        for i, chapter in enumerate(chapters):
            # --- 暂停/停止 ---
            while TASK_STATES.get(task_id) == "paused":
                time.sleep(1)
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
            if TASK_STATES.get(task_id) == "stopped":
                yield f"data: {json.dumps({'type': 'log', 'msg': '任务已终止'})}\n\n"
                break

            sec_title = chapter['title']
            
            # --- 父级节点 ---
            if chapter.get('is_parent', False):
                yield f"data: {json.dumps({'type': 'log', 'msg': f'>>> 章节标题: {sec_title}'})}\n\n"
                section_md = f"## {sec_title}\n\n" 
                full_content += section_md
                yield f"data: {json.dumps({'type': 'content', 'md': section_md})}\n\n"
                continue 

            # --- 叶子节点 ---
            target = int(chapter.get('words', 500))
            
            # 获取分配给该章节的参考文献
            ref_context = chapter_ref_map.get(i, "")
            
            log_msg = f"正在撰写 [{i+1}/{total_chapters}]: {sec_title}"
            if ref_context:
                ref_count = ref_context.count("ID_")
                log_msg += f" [智能分配 {ref_count} 篇文献]"
            
            yield f"data: {json.dumps({'type': 'log', 'msg': log_msg})}\n\n"
            
            sys_prompt = get_academic_thesis_prompt(target, ref_context, sec_title)
            user_prompt = f"论文题目：{title}\n当前章节：{sec_title}\n前文脉络：{context[-600:]}\n字数要求：{target}字"
            
            raw_content = self._call_llm(sys_prompt, user_prompt)
            final_content = ref_manager.process_text(raw_content)
            
            # --- 格式清洗（缩进/空行） ---
            lines = final_content.split('\n')
            formatted_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith('　　') and not line.startswith('#'):
                    line = '　　' + line # 强制缩进
                formatted_lines.append(line)
            final_content = '\n\n'.join(formatted_lines)

            # 扩写逻辑
            if "摘要" not in sec_title and len(final_content) < target * 0.6:
                yield f"data: {json.dumps({'type': 'log', 'msg': f'   - 字数不足，进行扩写...'})}\n\n"
                expand_prompt = sys_prompt + "\n内容篇幅不足，请在保持格式（全角缩进、阿拉伯数字）的前提下，增加细节分析。"
                added_raw = self._call_llm(expand_prompt, f"请扩写：\n{raw_content}")
                added_processed = ref_manager.process_text(added_raw)
                
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

# 路由部分 (保持不变)
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