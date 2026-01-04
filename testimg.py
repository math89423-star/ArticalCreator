from docx import Document
import os

# -------------------------- 关键配置 --------------------------
docx_path = r"C:\Users\Administrator\Desktop\开题报告.docx"  # 你的docx文件路径（绝对路径/相对路径均可）
# --------------------------------------------------------------

# 1. 检查文件是否存在
if not os.path.exists(docx_path):
    print(f"错误：未找到文件 {docx_path}")
    exit()

# 2. 打开docx文档
doc = Document(docx_path)

# 3. 遍历所有表格并提取内容
all_tables_data = []  # 存储所有表格的数据
for table_idx, table in enumerate(doc.tables, start=1):
    print(f"\n===== 表格 {table_idx} =====")
    table_data = []  # 存储当前表格的数据（二维列表）
    
    # 遍历表格的每一行
    for row_idx, row in enumerate(table.rows, start=1):
        row_data = []  # 存储当前行的单元格内容
        
        # 遍历当前行的每一列（单元格）
        for col_idx, cell in enumerate(row.cells, start=1):
            # 提取单元格文本（strip() 去除首尾空白，避免换行/空格干扰）
            cell_text = cell.text.strip()
            row_data.append(cell_text)
            # 打印单个单元格内容（可选，方便调试）
            print(f"行{row_idx}列{col_idx}：{cell_text if cell_text else '（空白）'}")
        
        table_data.append(row_data)
    
    all_tables_data.append(table_data)

# 4. （可选）将提取的数据转为DataFrame（需安装pandas，便于后续分析/保存）
try:
    import pandas as pd
    for i, table_data in enumerate(all_tables_data, start=1):
        df = pd.DataFrame(table_data)
        print(f"\n表格 {i} 的DataFrame格式：")
        print(df)
        # 保存为CSV（可选）
        df.to_csv(f"提取的表格{i}.csv", index=False, encoding="utf-8-sig")
        print(f"表格 {i} 已保存为：提取的表格{i}.csv")
except ImportError:
    print("\n提示：若需使用DataFrame功能，请安装pandas（pip install pandas）")