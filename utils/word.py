import re
import io
import os
import matplotlib.pyplot as plt
import seaborn as sns
import base64
import pandas as pd  
import numpy as np
from matplotlib import font_manager
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

def register_custom_font():
    """
    自动查找并加载中文字体
    查找顺序：本地文件 -> Linux常见字体 -> Windows常见字体
    """
    # 1. 定义可能的本地路径 (相对路径 + 绝对路径)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir) # 假设 word.py 在子目录，往上一级找
    
    possible_font_paths = [
        'SimHei.ttf',                       # 1. 当前运行目录
        os.path.join(current_dir, 'SimHei.ttf'), # 2. word.py 同级目录
        os.path.join(project_root, 'SimHei.ttf'),# 3. 项目根目录
        '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc', # 4. Linux 常见路径 (文泉驿)
        '/usr/share/fonts/truetype/arphic/ukai.ttc'       # 5. Linux 常见路径 (楷体)
    ]

    # 2. 尝试加载本地文件
    for font_path in possible_font_paths:
        if os.path.exists(font_path):
            try:
                prop = font_manager.FontProperties(fname=font_path)
                font_manager.fontManager.addfont(font_path)
                print(f"[Font] 成功加载字体文件: {font_path}")
                # 设置为全局默认
                plt.rcParams['font.sans-serif'] = [prop.get_name()]
                plt.rcParams['axes.unicode_minus'] = False
                return prop.get_name()
            except Exception as e:
                print(f"[Font] 尝试加载 {font_path} 失败: {e}")

    # 3. 如果本地文件都没找到，尝试系统已安装的字体名称
    # 优先 Linux 开源字体，后备 Windows 字体
    fonts_to_try = [
        'WenQuanYi Micro Hei',  # Linux 最常见
        'WenQuanYi Zen Hei', 
        'Noto Sans CJK SC',     # Google/Linux
        'Droid Sans Fallback',  # Android/Linux
        'SimHei',               # Windows
        'Microsoft YaHei',      # Windows
        'SimSun'                # Windows
    ]
    
    # 获取系统字体列表
    system_fonts = {f.name for f in font_manager.fontManager.ttflist}
    
    for f in fonts_to_try:
        if f in system_fonts:
            print(f"[Font] 使用系统安装字体: {f}")
            plt.rcParams['font.sans-serif'] = [f]
            plt.rcParams['axes.unicode_minus'] = False
            return f

    print("[Font] ❌ 警告: 未找到任何中文字体，中文将无法显示！请上传 SimHei.ttf 到项目目录。")
    return 'sans-serif' # 最后的兜底

# 初始化字体 (脚本加载时自动执行)
CURRENT_FONT_NAME = register_custom_font()

class TextCleaner:
    @staticmethod
    def clean_special_chars(text):
        text = text.replace('\u3000', '').replace('\u00A0', ' ').replace('\u200b', '')
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        return text
    
    @staticmethod
    def correct_punctuation(text):
        masks = {}
        def save_mask(match):
            key = f"__MASK_{len(masks)}__"
            masks[key] = match.group(0)
            return key

        text = re.sub(r'```[\s\S]*?```', save_mask, text)
        text = re.sub(r'`[^`\n]+`', save_mask, text)
        text = re.sub(r'!\[.*?\]\(.*?\)', save_mask, text)
        text = re.sub(r'\[.*?\]\(.*?\)', save_mask, text)
        
        # 智能标点替换
        text = re.sub(r'(?<=[\u4e00-\u9fa5]),', '，', text)
        text = re.sub(r',(?=[\u4e00-\u9fa5])', '，', text)
        text = re.sub(r'(?<=[\u4e00-\u9fa5])\.', '。', text) 
        text = re.sub(r'(?<=[\u4e00-\u9fa5]):', '：', text)
        text = re.sub(r':(?=[\u4e00-\u9fa5])', '：', text)
        text = re.sub(r'(?<=[\u4e00-\u9fa5]);', '；', text)
        text = re.sub(r';(?=[\u4e00-\u9fa5])', '；', text)
        text = re.sub(r'(?<=[\u4e00-\u9fa5])\?', '？', text)
        text = re.sub(r'\?(?=[\u4e00-\u9fa5])', '？', text)
        text = re.sub(r'(?<=[\u4e00-\u9fa5])!', '！', text)
        text = re.sub(r'!(?=[\u4e00-\u9fa5])', '！', text)
        text = re.sub(r'(?<=[\u4e00-\u9fa5])\s*\(', '（', text)
        text = re.sub(r'\((?=[\u4e00-\u9fa5])', '（', text)
        text = re.sub(r'(?<=[\u4e00-\u9fa5])\)', '）', text)
        text = re.sub(r'\)(?=[\u4e00-\u9fa5])', '）', text)

        def quote_replacer(match):
            content = match.group(1)
            if re.search(r'[\u4e00-\u9fa5]', content):
                return f'“{content}”'
            return match.group(0)
        text = re.sub(r'"(.*?)"', quote_replacer, text, flags=re.DOTALL)

        for key in reversed(list(masks.keys())):
            text = text.replace(key, masks[key])
        return text
    
    @staticmethod
    def convert_cn_numbers(text: str) -> str:
        return text

class MarkdownToDocx:
    @staticmethod
    def set_table_borders(table):
        tbl = table._tbl
        tblPr = tbl.tblPr
        for tag in ['w:tblStyle', 'w:tblBorders', 'w:tblLook']:
            element = tblPr.find(qn(tag))
            if element is not None: tblPr.remove(element)
        tblBorders = OxmlElement('w:tblBorders')
        def border(tag, val, sz, space="0", color="auto"):
            el = OxmlElement(f'w:{tag}')
            el.set(qn('w:val'), val)
            el.set(qn('w:sz'), str(sz))
            el.set(qn('w:space'), space)
            el.set(qn('w:color'), color)
            return el
        tblBorders.append(border('top', 'single', 12))
        tblBorders.append(border('bottom', 'single', 12))
        tblBorders.append(border('insideH', 'single', 4))
        tblBorders.append(border('left', 'nil', 0))
        tblBorders.append(border('right', 'nil', 0))
        tblBorders.append(border('insideV', 'nil', 0))
        tblPr.append(tblBorders)

    @staticmethod
    def create_error_image(error_msg):
        plt.close('all')
        plt.figure(figsize=(8, 4))
        plt.text(0.5, 0.5, f"Plot Error:\n{error_msg}", 
                 horizontalalignment='center', verticalalignment='center',
                 fontsize=12, color='red', bbox=dict(facecolor='#ffe6e6', edgecolor='red'))
        plt.axis('off')
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=100)
        plt.close('all')
        buf.seek(0)
        return buf

    @staticmethod
    def exec_python_plot(code_str):
        try:
            code_str = re.sub(r'^```python', '', code_str.strip(), flags=re.MULTILINE|re.IGNORECASE)
            code_str = re.sub(r'^```', '', code_str.strip(), flags=re.MULTILINE)
            code_str = code_str.replace('\u3000', ' ').replace('\u00A0', ' ').replace('\u200b', '')
            
            # 清洗配置
            code_str = re.sub(r"plt\.rcParams\[.*?\]\s*=\s*.*", "", code_str)
            code_str = re.sub(r"sns\.set_theme\(.*?\)", "", code_str) 
            code_str = re.sub(r"sns\.set\(.*?\)", "", code_str)

            plt.close('all') 
            plt.clf()
            
            # 强制应用字体配置
            sns.set_theme(style="whitegrid")
            plt.rcParams['font.sans-serif'] = [CURRENT_FONT_NAME]
            plt.rcParams['axes.unicode_minus'] = False

            local_vars = {'plt': plt, 'sns': sns, 'pd': pd, 'np': np}
            exec(code_str, {}, local_vars)
            
            buf = io.BytesIO()
            plt.tight_layout()
            plt.savefig(buf, format='png', dpi=300, bbox_inches='tight') 
            plt.close('all')
            buf.seek(0)
            return buf
        except Exception as e:
            print(f"Python Plot Error: {e}")
            return MarkdownToDocx.create_error_image(str(e))

    @staticmethod
    def parse_markdown_table(lines, start_idx):
        i = start_idx
        header_line = lines[i].strip()
        if not header_line.startswith('|'): return None, i
        headers = [c.strip() for c in header_line.strip('|').split('|')]
        i += 1
        if i < len(lines) and re.match(r'^[|\-\s:]+$', lines[i].strip()): i += 1
        else: return None, start_idx
        data = [headers]
        while i < len(lines):
            line = lines[i].strip()
            if not line.startswith('|'): break
            row = [c.strip() for c in line.strip('|').split('|')]
            if len(row) < len(headers): row += [''] * (len(headers) - len(row))
            else: row = row[:len(headers)]
            data.append(row)
            i += 1
        return data, i

    @staticmethod
    def convert(markdown_text):
        doc = Document()
        style = doc.styles['Normal']
        style.font.name = u'Times New Roman'
        style._element.rPr.rFonts.set(qn('w:eastAsia'), u'宋体')
        style.font.size = Pt(12)
        style.paragraph_format.line_spacing = 1.5
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = Pt(0)
        
        # 1. 基础清洗 (移除全角空格)
        markdown_text = TextCleaner.clean_special_chars(markdown_text)
        # 2. 标点修正
        markdown_text = TextCleaner.correct_punctuation(markdown_text)
        
        lines = markdown_text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip() # 使用 strip() 去除首尾空白
            if not line: 
                i += 1
                continue
            
            # 标题
            if line.startswith('#'):
                level = len(line.split(' ')[0])
                content = line.lstrip('#').strip()
                content = re.sub(r'^[•\*\-\s]+', '', content)
                doc_level = min(level, 3)
                heading = doc.add_heading('', level=doc_level)
                heading.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 1 else WD_ALIGN_PARAGRAPH.LEFT
                run = heading.add_run(content)
                run.font.name = u'Times New Roman'
                run._element.rPr.rFonts.set(qn('w:eastAsia'), u'黑体')
                run.font.color.rgb = RGBColor(0, 0, 0)
                heading.paragraph_format.keep_with_next = False
                if level == 1:
                    run.font.size = Pt(16)
                    heading.paragraph_format.space_before = Pt(12)
                    heading.paragraph_format.space_after = Pt(12)
                elif level == 2:
                    run.font.size = Pt(14)
                    heading.paragraph_format.space_before = Pt(12)
                    heading.paragraph_format.space_after = Pt(12)
                else:
                    run.font.size = Pt(13)
                    heading.paragraph_format.space_before = Pt(6)
                    heading.paragraph_format.space_after = Pt(6)
                i += 1
                continue
            
            # Base64 图片
            img_match = re.search(r'!\[.*?\]\(data:image\/png;base64,(.*?)\)', line)
            if not img_match:
                img_match = re.search(r'src=["\']data:image\/png;base64,(.*?)["\']', line)
            if img_match:
                try:
                    base64_str = img_match.group(1)
                    img_data = base64.b64decode(base64_str)
                    img_stream = io.BytesIO(img_data)
                    p = doc.add_paragraph()
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    run = p.add_run()
                    # 设置图片宽度为 14cm，适配 A4 纸
                    run.add_picture(img_stream, width=Cm(14)) 
                except Exception as e:
                    print(f"Base64 Image Error: {e}")
                i += 1
                continue

            # Python 代码块兜底
            if line.startswith('```python'):
                code_block = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_block.append(lines[i])
                    i += 1
                i += 1
                img_stream = MarkdownToDocx.exec_python_plot("\n".join(code_block))
                p = doc.add_paragraph()
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = p.add_run()
                if img_stream:
                    run.add_picture(img_stream, width=Cm(14))
                continue
            
            # 表格处理
            if line.startswith('|'):
                table_data, next_i = MarkdownToDocx.parse_markdown_table(lines, i)
                if table_data and len(table_data) > 1:
                    rows = len(table_data)
                    cols = max(len(r) for r in table_data)
                    if cols > 0:
                        table = doc.add_table(rows=rows, cols=cols)
                        table.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        table.autofit = True
                        for r, row_data in enumerate(table_data):
                            for c, cell_text in enumerate(row_data):
                                if c >= cols: break
                                cell = table.cell(r, c)
                                cell.text = ""
                                p = cell.paragraphs[0]
                                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                                clean_text = cell_text.replace('**', '').strip()
                                clean_text = TextCleaner.correct_punctuation(clean_text)
                                run = p.add_run(clean_text)
                                run.font.name = u'Times New Roman'
                                run._element.rPr.rFonts.set(qn('w:eastAsia'), u'宋体')
                                run.font.size = Pt(10.5)
                                if r == 0: run.bold = True
                        try: MarkdownToDocx.set_table_borders(table)
                        except: pass
                        doc.add_paragraph()
                        i = next_i
                        continue
            
            # 正文段落
            if line:
                clean_line = line.replace('**', '').strip() 
                line = TextCleaner.correct_punctuation(line)
                
                is_caption = re.match(r'^(图|表)\s*\d+[\.\-]\d+', clean_line) or re.match(r'^(图|表)\s*\d+', clean_line)
                p = doc.add_paragraph()
                if is_caption:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p.paragraph_format.first_line_indent = None
                    p.paragraph_format.space_before = Pt(6)
                    p.paragraph_format.space_after = Pt(6)
                else:
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                    # [关键修改] 恢复 Word 原生首行缩进 (24pt ≈ 2字符)
                    # 替代了之前的全角空格方案
                    p.paragraph_format.first_line_indent = Pt(24) 
                    
                    p.paragraph_format.line_spacing = 1.5
                    p.paragraph_format.space_after = Pt(0)
                    p.paragraph_format.space_before = Pt(0)
                
                parts = re.split(r'(\*\*.*?\*\*)', line)
                for part in parts:
                    if not part: continue
                    is_bold = part.startswith('**') and part.endswith('**')
                    text_content = part.replace('**', '') if is_bold else part
                    run = p.add_run(text_content)
                    run.font.name = u'Times New Roman'
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), u'宋体')
                    run.font.size = Pt(12)
                    run.bold = is_bold
            i += 1
        out_stream = io.BytesIO()
        doc.save(out_stream)
        out_stream.seek(0)
        return out_stream
    
class TextReportParser:
    @staticmethod
    def parse(text: str) -> dict:
        """
        解析开题报告文本，智能提取：题目、大纲、参考文献、文献综述
        [增强版] 支持英文大纲 (Chapter X, 1.1, Abstract...)
        """
        data = {
            "title": "",
            "outline_content": "",
            "cn_refs": [],
            "en_refs": [],
            "review": ""
        }
        
        if not text:
            return data

        # ==========================================
        # 1. 提取题目
        # ==========================================
        # 策略A: 显式标记 "题目：" or "Title:"
        title_match = re.search(r'(?:论文)?(?:题目|Title)[:：]\s*(.*)', text, re.IGNORECASE)
        if title_match:
            data["title"] = title_match.group(1).strip()
        else:
            # 策略B: 取第一行非空文本
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            if lines and len(lines[0]) < 100:
                data["title"] = lines[0]

        # ==========================================
        # 2. 提取参考文献 (先提取并移除，防止干扰大纲解析)
        # ==========================================
        # 查找“参考文献”或 "References"
        ref_split = re.split(r'^\s*(?:参考文献|References)[:：]?\s*$', text, flags=re.MULTILINE | re.IGNORECASE)
        
        main_body = text 
        
        if len(ref_split) > 1:
            ref_text = ref_split[-1].strip()
            main_body = ref_split[0] 
            
            refs = [line.strip() for line in ref_text.split('\n') if line.strip()]
            for ref in refs:
                # 清洗序号
                clean_ref = re.sub(r'^(\[\d+\]|\d+\.|（\d+）|\(\d+\))\s*', '', ref)
                if len(clean_ref) < 5: continue
                
                # 区分中英文
                if re.search(r'[\u4e00-\u9fa5]', clean_ref):
                    data["cn_refs"].append(clean_ref)
                else:
                    data["en_refs"].append(clean_ref)

        # ==========================================
        # 3. 提取文献综述 (Review)
        # ==========================================
        # 支持中文和英文关键词
        review_keywords = ["文献综述", "研究现状", "国内外研究", "Literature Review", "Related Work"]
        stop_keywords = r'(?:研究内容|研究方法|论文提纲|论文目录|第[一二三]章|3\.|^3\s|Chapter|Methodology|Research Content)'
        
        for kw in review_keywords:
            pattern = rf'{kw}[:：]?\s*([\s\S]*?)(?={stop_keywords}|$)'
            match = re.search(pattern, main_body, re.IGNORECASE | re.MULTILINE)
            if match:
                review_content = match.group(1).strip()
                if len(review_content) > 50:
                    data["review"] = review_content
                    break

        # ==========================================
        # 4. 提取大纲/目录 (核心修改部分)
        # ==========================================
        
        # 尝试定位目录区域
        outline_match = re.search(r'(?:目录|提纲|章节安排|结构安排|Table of Contents|Outline)[:：]?\s*([\s\S]*)', main_body, re.MULTILINE | re.IGNORECASE)
        source_for_outline = outline_match.group(1) if outline_match else main_body
        
        outline_lines = []
        raw_lines = source_for_outline.split('\n')
        
        # 定义大纲行的正则匹配规则
        outline_patterns = [
            r'^Chapter\s+\d+',             # Chapter 1...
            r'^Section\s+\d+',             # Section 1...
            r'^Part\s+\d+',                # Part 1...
            r'^第[一二三四五六七八九十0-9]+章', # 第一章...
            r'^\d+(\.\d+)*\s',             # 1.1 ... (注意末尾要有空格，避免匹配年份)
            r'^\d+\.\s',                   # 1. ...
            r'^[一二三四五六]+、',           # 一、...
            # 英文特定关键词
            r'^(?:Abstract|Introduction|Literature Review|Methodology|Results|Discussion|Conclusion|References|Appendix)',
            # 中文特定关键词
            r'^(?:摘要|绪论|结论|参考文献|致谢|附录)'
        ]
        
        combined_pattern = '|'.join(outline_patterns)
        
        for line in raw_lines:
            line = line.strip()
            # 排除过长的段落，只保留看起来像标题的行
            if len(line) < 100 and re.match(combined_pattern, line, re.IGNORECASE):
                outline_lines.append(line)
        
        if outline_lines:
            data["outline_content"] = "\n".join(outline_lines)

        return data