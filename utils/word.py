import re
import io
import matplotlib.pyplot as plt
import seaborn as sns
import unicodedata
import pandas as pd
import numpy as np
from docx import Document
from docx.shared import Pt, RGBColor, Cm, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


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
            
            # [核心修复] 强制清洗特殊空白符
            code_str = code_str.replace('\u3000', ' ').replace('\u00A0', ' ').replace('\u200b', '')
            
            # 2. 设置绘图环境 (解决中文乱码)
            plt.clf() # 清除旧图
            plt.figure(figsize=(6, 4)) # 适中的学术图表尺寸
            
            # 尝试加载中文字体
            fonts = ['SimHei', 'Microsoft YaHei', 'SimSun', 'Arial Unicode MS', 'WenQuanYi Micro Hei']
            font_found = False
            for f in fonts:
                try:
                    plt.rcParams['font.sans-serif'] = [f]
                    plt.rcParams['axes.unicode_minus'] = False # 负号显示
                    # 简单测试字体是否可用
                    fig = plt.figure()
                    fig.text(0, 0, "test", fontname=f)
                    plt.close(fig)
                    font_found = True
                    break
                except: continue
            
            if not font_found:
                print("Warning: No Chinese font found for matplotlib.")

            # 3. 注入上下文并执行
            local_vars = {'plt': plt, 'sns': sns, 'pd': pd, 'np': np}
            
            # 使用 seaborn 样式
            sns.set_theme(style="whitegrid")
            if font_found:
                 # 重新设置字体，因为 seaborn 可能覆盖了 rcParams
                 plt.rcParams['font.sans-serif'] = [f]
                 plt.rcParams['axes.unicode_minus'] = False

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
        if not header_line.startswith('|'): return None, i # 不是表格

        headers = [c.strip() for c in header_line.strip('|').split('|')]
        
        i += 1
        # 跳过分隔行 |---|
        if i < len(lines) and re.match(r'^[|\-\s:]+$', lines[i].strip()):
            i += 1
        else:
             # 如果没有分隔线，可能不是标准表格，或者只有一行
             # 这里假设必须有分隔线才算 Markdown 表格
             return None, start_idx

        data = [headers]
        while i < len(lines):
            line = lines[i].strip()
            if not line.startswith('|'): break
            
            # 提取数据
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
    def set_paragraph_format(paragraph, font_name=u'宋体', font_size=12, bold=False, alignment=None, first_line_indent=None, line_spacing=1.5):
        """统一设置段落格式"""
        if alignment is not None:
            paragraph.alignment = alignment
        
        paragraph_format = paragraph.paragraph_format
        paragraph_format.line_spacing = line_spacing
        
        if first_line_indent:
             paragraph_format.first_line_indent = first_line_indent

        for run in paragraph.runs:
            run.font.name = u'Times New Roman'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)
            run.font.size = Pt(font_size)
            run.bold = bold
            run.font.color.rgb = RGBColor(0, 0, 0)

    @staticmethod
    def convert(markdown_text):
        doc = Document()
        
        # --- 全局样式设置 ---
        style = doc.styles['Normal']
        style.font.name = u'Times New Roman'
        style._element.rPr.rFonts.set(qn('w:eastAsia'), u'宋体')
        style.font.size = Pt(12) # 小四
        style.paragraph_format.line_spacing = 1.5
        # [修复1] 全局强制去除段后间距，解决“空行”问题
        style.paragraph_format.space_before = Pt(0)
        style.paragraph_format.space_after = Pt(0)
        
        # 清洗文本中的特殊空白符
        markdown_text = TextCleaner.clean_special_chars(markdown_text)

        lines = markdown_text.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # --- 1. 标题 ---
            if line.startswith('#'):
                level = len(line.split(' ')[0])
                # [修复2] 清洗标题文本，去除可能存在的 Markdown 列表符或圆点
                content = line.lstrip('#').strip()
                content = re.sub(r'^[•\*\-\s]+', '', content)
                
                # 限制最大层级为 3，避免 Word 样式错乱
                doc_level = min(level, 3) 
                
                heading = doc.add_heading('', level=doc_level)
                
                # 标题格式：居中(一级) 或 左对齐，黑体
                heading.alignment = WD_ALIGN_PARAGRAPH.CENTER if level == 1 else WD_ALIGN_PARAGRAPH.LEFT
                
                run = heading.add_run(content)
                run.font.name = u'Times New Roman'
                run._element.rPr.rFonts.set(qn('w:eastAsia'), u'黑体') # 标题用黑体
                run.font.color.rgb = RGBColor(0, 0, 0) # 黑色
                
                # [修复2] 移除“与下段同页”属性，消除左侧小黑点（格式标记）
                heading.paragraph_format.keep_with_next = False
                
                # 字号设置
                if level == 1:
                    run.font.size = Pt(16) # 三号
                    heading.paragraph_format.space_before = Pt(12)
                    heading.paragraph_format.space_after = Pt(12)
                elif level == 2:
                    run.font.size = Pt(14) # 四号
                    heading.paragraph_format.space_before = Pt(12)
                    heading.paragraph_format.space_after = Pt(6)
                else:
                    run.font.size = Pt(13) # 小四
                    heading.paragraph_format.space_before = Pt(6)
                    heading.paragraph_format.space_after = Pt(6)

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
                    # 调整图片大小，不超过页面宽度
                    run = p.add_run()
                    run.add_picture(img_stream, width=Cm(14))
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
                    cols = max(len(r) for r in table_data) # 确保列数正确
                    if cols > 0:
                        # 添加表格前先判断是否需要图表标题
                        
                        table = doc.add_table(rows=rows, cols=cols)
                        table.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        table.autofit = True # 自动调整列宽
                        
                        for r, row_data in enumerate(table_data):
                            for c, cell_text in enumerate(row_data):
                                if c >= cols: break # 防止越界
                                cell = table.cell(r, c)
                                cell.text = "" # 清除默认
                                p = cell.paragraphs[0]
                                p.alignment = WD_ALIGN_PARAGRAPH.CENTER # 表格内容居中
                                
                                clean_text = cell_text.replace('**', '').strip()
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
                # 预处理：识别 Markdown 加粗
                # 逻辑优化：普通段落首行缩进，图表标题居中且不缩进
                
                # 判断是否为图表标题 (图1-1 / 表 2.1)
                clean_line = line.replace('**', '').strip()
                is_caption = re.match(r'^(图|表)\s*\d+[\.\-]\d+', clean_line) or re.match(r'^(图|表)\s*\d+', clean_line)
                
                p = doc.add_paragraph()
                
                if is_caption:
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    p_format = p.paragraph_format
                    p_format.first_line_indent = None # 标题不缩进
                    p_format.space_before = Pt(6)
                    p_format.space_after = Pt(6)
                else:
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY # 两端对齐
                    p_format = p.paragraph_format
                    p_format.first_line_indent = Pt(24) # 首行缩进2字符 (12pt * 2)
                    p_format.line_spacing = 1.5 # 1.5倍行距
                    # [修复1] 显式去除段后间距，防止出现视觉上的“空行”
                    p_format.space_after = Pt(0)
                    p_format.space_before = Pt(0)

                # 解析加粗语法
                parts = re.split(r'(\*\*.*?\*\*)', line)
                for part in parts:
                    if not part: continue
                    
                    is_bold = part.startswith('**') and part.endswith('**')
                    text_content = part.replace('**', '') if is_bold else part
                    
                    run = p.add_run(text_content)
                    run.font.name = u'Times New Roman'
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), u'宋体')
                    run.font.size = Pt(12) # 小四
                    run.bold = is_bold
                    
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
    def clean_special_chars(text):
        """清洗不可见字符和特殊格式"""
        # 1. 替换全角空格和其他特殊空白
        text = text.replace('\u3000', ' ').replace('\u00A0', ' ').replace('\u200b', '')
        # 2. 统一换行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        return text

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