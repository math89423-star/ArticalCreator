import re
import io
import matplotlib.pyplot as plt
import seaborn as sns
import unicodedata
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
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
            
            # [核心修复] 强制清洗特殊空白符，防止 SyntaxError: invalid character in identifier
            # \u3000: 全角空格, \u00A0: NBSP, \u200b: 零宽空格
            code_str = code_str.replace('\u3000', ' ').replace('\u00A0', ' ').replace('\u200b', '')
            
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