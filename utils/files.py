# utils/files.py
import pandas as pd
import pypdf
import docx

def extract_file_content(file_stream, filename) -> str:
    """
    根据文件后缀名，提取文件内容为纯文本字符串。
    使用 XML 标签包裹内容，便于 LLM 区分不同文件来源
    """
    filename = filename.lower()
    raw_text = "" 
    
    try:
        # 重置指针
        if hasattr(file_stream, 'seek'):
            file_stream.seek(0)

        # 1. Excel/CSV
        if filename.endswith('.csv'):
            try:
                df = pd.read_csv(file_stream)
            except UnicodeDecodeError:
                file_stream.seek(0)
                df = pd.read_csv(file_stream, encoding='gbk')
            raw_text = df.head(60).to_markdown(index=False)
        
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file_stream)
            raw_text = df.head(60).to_markdown(index=False)
            
        # 2. TXT
        elif filename.endswith('.txt'):
            try:
                raw_text = file_stream.read().decode('utf-8')
            except:
                file_stream.seek(0)
                raw_text = file_stream.read().decode('gbk', errors='ignore')
            raw_text = raw_text[:8000] 
            
        # 3. PDF
        elif filename.endswith('.pdf'):
            reader = pypdf.PdfReader(file_stream)
            for i, page in enumerate(reader.pages[:15]): 
                page_text = page.extract_text()
                if page_text: 
                    raw_text += f"[Page {i+1}] {page_text}\n"

        # 4. DOCX
        elif filename.endswith('.docx'):
            doc = docx.Document(file_stream)
            for para in doc.paragraphs:
                if para.text.strip():
                    raw_text += para.text + "\n"
            for table in doc.tables:
                for row in table.rows:
                    row_text = [cell.text.strip() for cell in row.cells]
                    raw_text += " | ".join(row_text) + "\n"
            raw_text = raw_text[:8000]

        else:
            return f"" 
            
    except Exception as e:
        print(f"解析文件 {filename} 失败: {e}")
        return "" 

    return f"""
<datasource name="{filename}">
{raw_text}
</datasource>
"""