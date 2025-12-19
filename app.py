import time
import json
import re
import math
import io
import requests
import unicodedata
import base64
import matplotlib
# 设置后端为 Agg，确保在无显示器的服务器环境下也能运行
matplotlib.use('Agg') 
import matplotlib.pyplot as plt
import seaborn as sns
from typing import List, Dict, Generator, Tuple
from flask import Flask, render_template, request, Response, stream_with_context, jsonify, send_file
from openai import OpenAI
from docx import Document
from docx.shared import Pt, Inches, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

app = Flask(__name__)

# ==============================================================================
# 配置区域
# ==============================================================================
API_KEY = "sk-VuSl3xg7XTQUbWzs4QCeinJk70H4rhFUtrLdZlBC6hvjvs1t" # 替换 Key
BASE_URL = "https://tb.api.mkeai.com/v1"
MODEL_NAME = "deepseek-v3.2" 

TASK_STATES = {}

# ==============================================================================
# 工具类：Word 文档生成器 (Python绘图 + 强力三线表)
# ==============================================================================
class MarkdownToDocx:
    @staticmethod
    def set_table_borders(table):
        """
        强制应用学术三线表样式 (底层XML暴力写入)
        规则：顶底粗线(1.5pt/sz=12)，内部横线细线(0.5pt/sz=4)，无竖线
        """
        tbl = table._tbl
        tblPr = tbl.tblPr
        
        # 1. 彻底清除所有样式干扰
        for tag in ['w:tblStyle', 'w:tblBorders', 'w:tblLook']:
            element = tblPr.find(qn(tag))
            if element is not None:
                tblPr.remove(element)
            
        # 2. 定义新的边框 XML
        tblBorders = OxmlElement('w:tblBorders')
        
        def border(tag, val, sz, space="0", color="auto"):
            el = OxmlElement(f'w:{tag}')
            el.set(qn('w:val'), val)
            el.set(qn('w:sz'), str(sz))
            el.set(qn('w:space'), space)
            el.set(qn('w:color'), color)
            return el

        # 顶线 (粗 1.5pt -> sz=12)
        tblBorders.append(border('top', 'single', 12))
        # 底线 (粗 1.5pt -> sz=12)
        tblBorders.append(border('bottom', 'single', 12))
        # 内部横线 (细 0.5pt -> sz=4)
        tblBorders.append(border('insideH', 'single', 4))
        # 竖线 (无)
        tblBorders.append(border('left', 'nil', 0))
        tblBorders.append(border('right', 'nil', 0))
        tblBorders.append(border('insideV', 'nil', 0))

        tblPr.append(tblBorders)

    @staticmethod
    def exec_python_plot(code_str):
        """执行 LLM 生成的 Python 代码并返回图片流"""
        try:
            # 1. 代码清洗
            code_str = re.sub(r'^```python', '', code_str.strip(), flags=re.MULTILINE|re.IGNORECASE)
            code_str = re.sub(r'^```', '', code_str.strip(), flags=re.MULTILINE)
            
            # 2. 设置绘图环境 (解决中文乱码)
            plt.clf() # 清除旧图
            plt.figure(figsize=(6, 4)) # 适中的学术图表尺寸
            
            # 尝试加载中文字体
            fonts = ['SimHei', 'Microsoft YaHei', 'SimSun', 'Arial Unicode MS']
            for f in fonts:
                try:
                    plt.rcParams['font.sans-serif'] = [f]
                    # 简单测试字体是否可用
                    fig = plt.figure()
                    fig.text(0, 0, "test", fontname=f)
                    plt.close(fig)
                    break
                except: continue
            plt.rcParams['axes.unicode_minus'] = False # 负号显示
            
            # 3. 注入上下文并执行
            import pandas as pd
            import numpy as np
            local_vars = {'plt': plt, 'sns': sns, 'pd': pd, 'np': np}
            
            exec(code_str, {}, local_vars)
            
            # 4. 保存图片到内存
            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format='png', dpi=300) # 高清 300 DPI
            plt.close()
            buf.seek(0)
            return buf
        except Exception as e:
            print(f"Python Plot Error: {e}")
            return None

    @staticmethod
    def parse_markdown_table(lines, start_idx):
        """解析 Markdown 表格"""
        i = start_idx
        # 清洗首行
        header_line = lines[i].strip()
        headers = [c.strip() for c in header_line.strip('|').split('|') if c.strip()]
        if not headers: return None, i + 1
        
        i += 1
        # 跳过分隔行 |---|
        if i < len(lines) and re.match(r'^[|\-\s:]+$', lines[i].strip()):
            i += 1
        
        data = [headers]
        while i < len(lines):
            line = lines[i].strip()
            if not line.startswith('|'): break
            
            # 提取数据，忽略空字符串
            row = [c.strip() for c in line.strip('|').split('|')]
            # 补齐或截断列数
            if len(row) < len(headers):
                row += [''] * (len(headers) - len(row))
            else:
                row = row[:len(headers)]
                
            data.append(row)
            i += 1
        return data, i

    @staticmethod
    def convert(markdown_text):
        doc = Document()
        # 全局样式：中文宋体，西文 Times New Roman
        style = doc.styles['Normal']
        style.font.name = u'Times New Roman'
        style._element.rPr.rFonts.set(qn('w:eastAsia'), u'宋体')
        style.paragraph_format.line_spacing = 1.5

        lines = markdown_text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # --- 1. 标题 ---
            if line.startswith('#'):
                level = len(line.split(' ')[0])
                content = line.lstrip('#').strip()
                heading = doc.add_heading('', level=min(level, 9))
                heading.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 1 else WD_ALIGN_PARAGRAPH.LEFT
                run = heading.add_run(content)
                run.font.name = u'黑体' if level == 1 else u'宋体'
                run._element.rPr.rFonts.set(qn('w:eastAsia'), u'黑体' if level == 1 else u'宋体')
                run.font.color.rgb = RGBColor(0, 0, 0)
                run.font.size = Pt(16 if level==1 else 14)
                i += 1
                continue

            # --- 2. Python 代码绘图 ---
            if line.startswith('```python'):
                code_block = []
                i += 1 
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_block.append(lines[i])
                    i += 1
                i += 1 # 跳过结束符
                
                # 执行 Python 代码
                img_stream = MarkdownToDocx.exec_python_plot("\n".join(code_block))
                
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if img_stream:
                    p.add_run().add_picture(img_stream, width=Cm(14))
                else:
                    # 失败时显示红色提示
                    run = p.add_run("[图表生成失败: 代码执行错误，请检查日志]")
                    run.font.color.rgb = RGBColor(255, 0, 0)
                continue

            # --- 3. 表格 (三线表) ---
            if line.startswith('|'):
                table_data, next_i = MarkdownToDocx.parse_markdown_table(lines, i)
                if table_data and len(table_data) > 1:
                    rows = len(table_data)
                    cols = len(table_data[0])
                    if cols > 0:
                        table = doc.add_table(rows=rows, cols=cols)
                        table.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        table.autofit = True
                        
                        for r, row_data in enumerate(table_data):
                            for c, cell_text in enumerate(row_data):
                                cell = table.cell(r, c)
                                cell.text = "" # 清除默认
                                p = cell.paragraphs[0]
                                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                                
                                clean_text = cell_text.replace('**', '')
                                run = p.add_run(clean_text)
                                run.font.name = u'Times New Roman'
                                run._element.rPr.rFonts.set(qn('w:eastAsia'), u'宋体')
                                run.font.size = Pt(10.5) # 五号字
                                if r == 0: run.bold = True # 表头加粗

                        # 强制应用三线表边框
                        try:
                            MarkdownToDocx.set_table_borders(table)
                        except Exception as e:
                            print(f"Table border error: {e}")
                        
                        doc.add_paragraph() # 表后空行
                        i = next_i
                        continue
            
            # --- 4. 普通段落 ---
            if line:
                p = doc.add_paragraph()
                # 识别图表标题并居中 (图1.1 / 表1.1)
                clean_line = line.replace('**', '').strip()
                if re.match(r'^(图|表)\s*\d', clean_line) or re.match(r'^(图|表)\d', clean_line):
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                
                parts = re.split(r'(\*\*.*?\*\*)', line)
                for part in parts:
                    clean_part = part.replace('**', '')
                    if not clean_part: continue
                    run = p.add_run(clean_part)
                    run.font.name = u'Times New Roman'
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), u'宋体')
                    if part.startswith('**'): run.bold = True
            
            i += 1
            
        out_stream = io.BytesIO()
        doc.save(out_stream)
        out_stream.seek(0)
        return out_stream

# ==============================================================================
# 工具类：文本清洗
# ==============================================================================
class TextCleaner:
    @staticmethod
    def convert_cn_numbers(text: str) -> str:
        # 保护 Python 代码块不被清洗
        code_blocks = {}
        def save_code(match):
            key = f"__CODE_{len(code_blocks)}__"
            code_blocks[key] = match.group(0)
            return key
        
        # 保护 ```python ... ``` 和 ```mermaid ... ```
        text = re.sub(r'```.*?```', save_code, text, flags=re.DOTALL)
        
        # 全角转半角 (国际标准 NFKC)
        text = unicodedata.normalize('NFKC', text)

        # 中文年份转换
        def year_repl(match):
            cn_map = {'零':'0','一':'1','二':'2','三':'3','四':'4','五':'5','六':'6','七':'7','八':'8','九':'9'}
            return "".join([cn_map.get(c, c) for c in match.group(1)]) + "年"
        text = re.sub(r'([零一二三四五六七八九]{4})年', year_repl, text)
        text = text.replace("百分之", "").replace("％", "%") 
        
        # 还原代码块
        for key, val in code_blocks.items():
            text = text.replace(key, val)
        return text

# ==============================================================================
# 引用管理器
# ==============================================================================
class ReferenceManager:
    def __init__(self, raw_references: str):
        raw_lines = [r.strip() for r in raw_references.split('\n') if r.strip()]
        self.all_refs = []
        clean_pattern = re.compile(r'^(\[\d+\]|\d+\.|（\d+）|\(\d+\))\s*')
        for line in raw_lines:
            cleaned_line = clean_pattern.sub('', line)
            self.all_refs.append(cleaned_line)
        self.current_chapter_refs = []

    def is_chinese(self, text: str) -> bool:
        return bool(re.search(r'[\u4e00-\u9fa5]', text))

    def distribute_references_smart(self, chapters: List[Dict]) -> Dict[int, List[Tuple[int, str]]]:
        if not self.all_refs: return {}
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

            if any(k in title for k in ["现状", "综述", "Review", "Status", "背景"]):
                if "国内" in title or "我国" in title or "China" in title:
                    domestic_idxs.append(i)
                elif "国外" in title or "国际" in title or "Foreign" in title:
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
        rem_all = rem_cn + rem_en
        rem_all.sort(key=lambda x: x[0])
        rem_final = assign_chunks(rem_all, general_idxs)

        if rem_final and last_content_idx != -1:
             if last_content_idx not in allocation: allocation[last_content_idx] = []
             allocation[last_content_idx].extend(rem_final)

        for idx in allocation:
            allocation[idx].sort(key=lambda x: x[0])
        return allocation

    def set_current_chapter_refs(self, refs: List[Tuple[int, str]]):
        self.current_chapter_refs = list(refs) 

    def process_text_deterministic(self, text: str) -> str:
        result_text = ""
        parts = text.split('[REF]')
        for i, part in enumerate(parts):
            result_text += part
            if i < len(parts) - 1:
                if self.current_chapter_refs:
                    global_id, _ = self.current_chapter_refs.pop(0)
                    result_text += f"[{global_id}]"
        
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
# Prompt Generation
# ==============================================================================
def get_academic_thesis_prompt(target_words: int, ref_content_list: List[str], current_chapter_title: str, chapter_num: str) -> str:
    
    # ------------------------------------------------------------------
    # 1. 章节专属逻辑
    # ------------------------------------------------------------------
    section_rule = ""
    is_abstract = "摘要" in current_chapter_title or "Abstract" in current_chapter_title
    
    # 判断是否为需要图表的章节 (核心修复)
    # 只有包含以下关键词的章节才启用图表
    needs_charts = False
    if chapter_num and any(k in current_chapter_title for k in ["实验", "测试", "分析", "结果", "数据", "设计", "实现", "验证", "Evaluation", "Analysis", "Design"]):
        needs_charts = True
    
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

    # C. 国内外研究现状
    elif any(k in current_chapter_title for k in ["现状", "综述", "Review"]):
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

    # G. 通用正文 (新增数据分析要求)
    else:
        section_rule = """
**当前任务：撰写正文分析**
1. **逻辑主导**: 核心是分析思路。
2. **深度论述**: 每一段都要有观点、有论据（数据或理论）、有结论。
"""

    # ------------------------------------------------------------------
    # 2. 引用指令
    # ------------------------------------------------------------------
    ref_instruction = ""
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

    # ----------------- 策略F: 更新为 Python 绘图 -----------------
    visuals_instruction = ""
    if needs_charts:
        visuals_instruction = f"""
### **策略F: 图表与数据可视化 (Python & Tables)**
**本章节必须包含图表**。请按以下规范生成：

1.  **表格**:
    -   使用 Markdown 表格语法。
    -   **表名**: 在表格**上方**，格式：`**表{chapter_num}.X 表名**`。
2.  **统计图 (Python Matplotlib)**:
    -   请编写一段**可直接运行的 Python 代码**来绘制图表。
    -   **代码块格式**: 使用 ` ```python ` 包裹。
    -   **要求**: 
        -   导入 `matplotlib.pyplot as plt`。
        -   **数据自包含**: 直接在代码中定义数据（列表或字典），**严禁**读取外部 csv/excel 文件。
        -   **字体**: 使用通用设置 `plt.rcParams['font.sans-serif'] = ['SimHei']` 以支持中文。
        -   **风格**: `plt.style.use('seaborn-v0_8-whitegrid')` 或类似学术风格。
        -   最后**不需要** `plt.show()` 或 `plt.savefig`，后端会自动捕获。
    -   **图名**: 在代码块**下方**，格式：`**图{chapter_num}.X 图名**`。
3.  **互动**: 正文必须包含 “如表{chapter_num}.1所示” 或 “如图{chapter_num}.1可见”。
"""
    else:
        visuals_instruction = "### **策略F: 图表禁令**\n**严禁生成任何图表。**"

    # ----------------- 最终组合 (策略A-E保持原样) -----------------
    return f"""
# 角色
你现在扮演一位**严谨的学术导师**，辅助学生撰写毕业论文。
任务：严格遵循特定的写作模板，保证学术规范，**绝不夸大成果**，**图文并茂**。

### **策略A: 格式与排版**
1.  **段落缩进**: **所有段落开头必须包含两个全角空格（　　）**。
2.  **禁用列表**: 严禁使用 Markdown 列表，必须写成连贯段落（研究方法除外）。


### **策略B: 数据与谦抑性 (CRITICAL)**
1.  **字体规范**: **所有数字、字母、标点必须使用半角字符 (Half-width)**。
    -   正确: 2023, 50%, "Method"
    -   错误: ２０２３, ５０％, “Method”
2.  **严禁夸大**: 
    -   **禁止**: “填补空白”、“国内首创”、“完美解决”。
    -   **必须用**: “丰富了...视角”、“提供了实证参考”、“优化了...”。


### **策略C: 章节专属逻辑**
{section_rule}

{ref_instruction}

{visuals_instruction}

### **策略E: 字数控制**
{word_count_strategy}

请开始写作。
"""

# ==============================================================================
# Agent
# ==============================================================================
class PaperAutoWriter:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.7, stream=False
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"[Error: {str(e)}]"

    def _research_phase(self, topic: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "严谨数据分析师。列出关于主题的真实数据、政策。使用半角数字。"},
                    {"role": "user", "content": f"检索关于'{topic}'的真实事实："}
                ],
                temperature=0.3, stream=False
            )
            return response.choices[0].message.content.strip()
        except: return ""

    def _extract_chapter_num(self, title: str) -> str:
        match_digit = re.match(r'^(\d+)', title.strip())
        if match_digit: return match_digit.group(1)
        match_cn = re.match(r'^第([一二三四五六七八九十]+)[章|部分]', title.strip())
        if match_cn:
            cn_map = {'一':'1','二':'2','三':'3','四':'4','五':'5','六':'6','七':'7','八':'8','九':'9','十':'10'}
            return cn_map.get(match_cn.group(1), "")
        return ""

    def generate_stream(self, task_id: str, title: str, chapters: List[Dict], references_raw: str) -> Generator[str, None, None]:
        ref_manager = ReferenceManager(references_raw)
        yield f"data: {json.dumps({'type': 'log', 'msg': '初始化...'})}\n\n"
        chapter_ref_map = ref_manager.distribute_references_smart(chapters)
        full_content = f"# {title}\n\n"
        context = "论文开头"
        
        for i, chapter in enumerate(chapters):
            while TASK_STATES.get(task_id) == "paused": time.sleep(1)
            if TASK_STATES.get(task_id) == "stopped": break

            sec_title = chapter['title']
            if chapter.get('is_parent', False):
                full_content += f"## {sec_title}\n\n"
                yield f"data: {json.dumps({'type': 'content', 'md': f'## {sec_title}\n\n'})}\n\n"
                continue

            target = int(chapter.get('words', 500))
            assigned_refs = chapter_ref_map.get(i, [])
            ref_manager.set_current_chapter_refs(assigned_refs)
            chapter_num = self._extract_chapter_num(sec_title)
            
            yield f"data: {json.dumps({'type': 'log', 'msg': f'正在撰写: {sec_title}'})}\n\n"
            
            facts_context = ""
            if "摘要" not in sec_title and "结论" not in sec_title:
                facts = self._research_phase(f"{title} - {sec_title}")
                if facts:
                    facts = TextCleaner.convert_cn_numbers(facts)
                    facts_context = f"\n【真实事实】:\n{facts}"

            sys_prompt = get_academic_thesis_prompt(target, [r[1] for r in assigned_refs], sec_title, chapter_num)
            user_prompt = f"题目：{title}\n章节：{sec_title}\n前文：{context[-600:]}\n字数：{target}\n{facts_context}"
            
            raw_content = self._call_llm(sys_prompt, user_prompt)
            processed_content = ref_manager.process_text_deterministic(raw_content)
            processed_content = TextCleaner.convert_cn_numbers(processed_content)
            
            lines = processed_content.split('\n')
            formatted_lines = []
            for line in lines:
                line = line.strip()
                if (line and not line.startswith('　　') and not line.startswith('#') and 
                    not line.startswith('|') and not line.startswith('```') and "import" not in line and "plt." not in line):
                    line = '　　' + line 
                formatted_lines.append(line)
            final_content = '\n\n'.join(formatted_lines)

            section_md = f"## {sec_title}\n\n{final_content}\n\n"
            full_content += section_md
            context = final_content
            yield f"data: {json.dumps({'type': 'content', 'md': section_md})}\n\n"

        if TASK_STATES.get(task_id) != "stopped":
            bib = ref_manager.generate_bibliography()
            full_content += bib
            yield f"data: {json.dumps({'type': 'content', 'md': bib})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        
        if task_id in TASK_STATES: del TASK_STATES[task_id]

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