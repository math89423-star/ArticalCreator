import re
import json
import time
from typing import List, Dict, Generator
from openai import OpenAI
from .reference import ReferenceManager
from .word import TextCleaner
import concurrent.futures

def get_rewrite_prompt(thesis_title: str, section_title: str, user_instruction: str, context_summary: str, custom_data: str, original_content: str) -> str:
    
    # 1. 动态生成上下文指令
    context_logic_instruction = ""
    
    # 如果前文很少（说明是开头部分），指令要强调“开篇”
    if not context_summary or len(context_summary) < 50:
        context_logic_instruction = """
   - **位置判断**: 当前检测为**论文/章节的起始部分**。
   - **写作逻辑**: 必须**开篇明义**，直接引入主题，**严禁**使用“承接上文”、“综上所述”、“如前所述”等过渡词。应奠定基调，引出后续内容。
"""
    # 如果是“结论/总结”类章节，指令要强调“收束”
    elif any(k in section_title for k in ["结论", "总结", "展望", "结语"]):
        context_logic_instruction = f"""
   - **位置判断**: 当前为**结论/收尾部分**。
   - **前文摘要**: "...{context_summary[-300:]}..."
   - **写作逻辑**: 必须对前文（尤其是摘要中提到的分析）进行**高屋建瓴的总结**，而不是简单的重复。要对全文进行收束，升华主题，并展望未来。
"""
    # 否则默认为“中间部分”，指令强调“承上启下”
    else:
        context_logic_instruction = f"""
   - **位置判断**: 当前为**论文中间章节**。
   - **前文摘要**: "...{context_summary[-500:]}..."
   - **写作逻辑**: 必须**紧密承接**上述前文的逻辑流。
     - 如果前文在分析问题，本段应继续深入或转向对策；
     - 如果前文是理论，本段应转向应用或实证。
     - **必须**使用恰当的学术过渡词（如“基于上述分析”、“具体而言”、“与此同时”）来确保文气贯通，避免突兀。
"""
    return f"""
# 角色
你是一位资深的学术论文评审与修改专家，擅长修正论文逻辑，确保论证严密、主题聚焦。

# 核心任务
你正在对论文 **《{thesis_title}》** 中的 **“{section_title}”** 章节进行重写。

# 关键上下文与逻辑约束 (Context)
1. **宏观一致性 (题目)**: 
   - 论文题目: 《{thesis_title}》
   - *红线*: 你重写的所有内容，必须**严格服务于**这个总标题。**严禁**撰写与该主题无关的通用废话。
   
2. **微观聚焦 (章节)**: 
   - 当前章节: “{section_title}”
   - *红线*: 内容必须精准聚焦于该小节的特定论点。
     - 如果标题是“现状”，就只写现状，不要写对策；
     - 如果标题是“原因”，就只写原因，不要写影响。
     - **严禁越界**去写其他章节的内容。

3. **上下文连贯性 (Flow)**: {context_logic_instruction}

4. **原文基础 (Reference Base)**:
   - **原文内容**: 
     ```
     {original_content[:2000]} 
     ```
   - **处理策略**: 
     - 用户的意图通常是在**原文基础上进行润色、修正或扩充**。
     - **除非**用户指令明确要求“完全重写”、“推翻重来”，否则请**保留原文的核心观点和数据**，重点优化其表达、逻辑结构和学术规范性。
     - 如果原文非常简陋，请进行**扩写和深化**。


# 用户修改指令 (最高优先级 - 必须满足)
{user_instruction}

# 严格排版与写作规范
1. **排版格式 (Machine Readable)**:
   - **首行缩进**: 输出的**每一个自然段**，开头必须包含**两个全角空格** (　　)。
   - **段间距**: 段落之间使用**单换行** (`\\n`)，**严禁**使用空行 (`\\n\\n`)。
   - **纯净输出**: **严禁**输出章节标题（如 "### {section_title}"），**严禁**包含“好的”、“根据要求”等对话内容。只输出正文。
2. **数据使用**:
   - 参考数据: {custom_data[:500]}...
   - 如果用户提供了数据，请优先使用并进行分析；如果没有，请基于通用学术逻辑撰写。

请开始重写，直接输出正文，注意格式排版。
"""

def get_academic_thesis_prompt(target_words: int, ref_content_list: List[str], current_chapter_title: str, chapter_num: str, has_user_data: bool = False, full_outline: str = "") -> str:
    
    # ------------------------------------------------------------------
    # 1. 章节专属逻辑
    # ------------------------------------------------------------------
    section_rule = ""
    is_cn_abstract = "摘要" in current_chapter_title
    is_en_abstract = "Abstract" in current_chapter_title and "摘要" not in current_chapter_title

    # 判断是否为需要图表的章节
    # [修改点1] 逻辑升级：如果章节名包含特定词 OR 挂载了用户数据，则必须开启图表
    needs_charts = False
    keywords = ["实验", "测试", "分析", "结果", "数据", "设计", "实现", "验证", "Evaluation", "Analysis", "Design"]
    if (chapter_num and any(k in current_chapter_title for k in keywords)) or has_user_data:
        needs_charts = True
    
    # A. 摘要
    if is_cn_abstract:
        section_rule = """
**当前任务：撰写摘要与关键词**
**红线规则**: 
1. **严禁输出标题**: 不要输出 "### 摘要" 或 "### Abstract"，直接开始写正文。
2. **中英对照**: 先写中文部分，再写英文部分。若没有英文（Abstract）部分则不写英文部分。

**逻辑结构**:
1. **研究背景**: 简述背景（约50字）。
2. **方法创新**: 做了什么，用了什么方法（约100字）。
3. **关键发现**: 得到了什么数据或结论（约100字）。
4. **理论贡献**: 价值是什么（约50字）。

**格式模板**:
   - 直接输出摘要正文。
   - 最后一行输出：**关键词**：词1；词2；词3
"""

    elif is_en_abstract:
        section_rule = """
**Current Task: Write English Abstract & Keywords**
**Requirements**:
1. **Language**: MUST be written in **English** only. No Chinese allowed.
2. **Content**: Translate the logic of a standard academic abstract (Background -> Method -> Results -> Conclusion).
3. **Format**: 
   - Output the abstract body directly.
   - Last line: **Keywords**: Word1; Word2; Word3
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
    elif any(k in current_chapter_title for k in ["国内研究现状", "国外研究现状", "文献综述", "Review", "Status", "文献述评", "Literature"]):
        if ref_content_list:
            first_ref = ref_content_list[0]
            if len(ref_content_list) > 1:
                other_refs_prompt = "\n".join([f"{{文献{i+2}}}: {ref}" for i, ref in enumerate(ref_content_list[1:])])
            else:
                other_refs_prompt = "无后续文献"
            
            section_rule = f"""
**当前任务：撰写研究现状 (文献综述)**
**核心目标**：将提供的参考文献列表转化为逻辑通顺的学术评述。

### **引用规范**
1.  **禁止出现ID**: 正文中**绝对禁止**出现 "参考文献ID"、"文献1" 等字样。
2.  **引用格式**: 必须从文献内容中提取**作者**和**年份**，格式为 `作者(年份)`。
    -   *引用示例*: "张三（2025）认为咖啡不好喝是因为不够甜。"
3.  **禁止模糊**: 严禁使用 "某学者"、"有研究" 等指代不明的词，**必须指名道姓**。
4.  **顺序与频次**: 必须**严格按照列表顺序**逐一论述。

### **写作逻辑**
1.  **第一段 (导语)**: 简要概括该领域的总体发展趋势（约80字）。
2.  **第二段 (核心综述)**: 
    -   **首条详述**: 针对 **{{文献1}}** ({first_ref}) 进行详细评述（约150字）。写明：作者+年份+核心贡献+局限性。
    -   **后续串联**: 依次对 **{{文献2}}** 及后续文献进行评述。
        -   使用连接词（如"与之类似"、"然而"、"在此基础上"）将不同文献逻辑串联。
3.  **第三段 (评述)**: 总结上述文献的共同不足，引出本研究的切入点。

**待综述的文献列表 (请从中提取信息)**:
- {{文献1}}: {first_ref}
{other_refs_prompt}
"""
        else:
            section_rule = "**当前任务：撰写研究现状**\n请基于通用学术知识撰写，保持总分总结构，引用真实存在的经典文献。"

    # D. 文献述评
    elif "述评" in current_chapter_title:
        section_rule = """
**当前任务：撰写文献述评**
**写作要求**: 
1. **不引用**: 此部分不需要引用具体文献。
2. **内容**: 总结前文文献的不足，需要对全部文献做出总结，归纳这些文献带来的启示，对本研究的影响，本研究能从文献中借鉴和学习到的内容，阐述研究的不足，以及需要丰富的内容等等。
3. **字数与篇幅要求**: 只写一个段落，约300字左右。
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

"""

    # ------------------------------------------------------------------
    # 2. 引用指令
    # ------------------------------------------------------------------
    ref_instruction = ""
    
    # 定义属于“综述/现状”的关键词
    review_keywords = ["国内研究现状", "国外研究现状", "文献综述", "Review", "Status", "文献述评", "Literature"]
    is_review_chapter = any(k in current_chapter_title for k in review_keywords)

    if ref_content_list and is_review_chapter:
        # 只有在综述章节，才强制要求引用
        ref_instruction = f"""
### **策略D: 引用执行 (Token Strategy)**
本章节**必须**引用分配的文献。
1.  **不要生成序号**: 不要写 [1] [2]。
2.  **插入标记**: 在提到文献观点时，必须插入 **`[REF]`** 标记。
3.  **数量**: 必须插入 {len(ref_content_list)} 个 `[REF]` 标记。
4.  **关联**: 即使文献不完全相关，也要用“此外，也有研究指出...”强行关联，**自圆其说**。
"""
    else:
        # 其他章节（如绪论、理论、实证、结论等）严禁引用
        ref_instruction = """
### **策略D: 引用禁令 (Citation Ban)**
**本章节严禁引用参考文献列表**。
1.  **绝对禁止**使用 `[REF]` 标记。
2.  **绝对禁止**提及“文献[x]”、“某学者指出”、“已有研究表明”等综述性语言。
3.  请完全基于**理论推导**、**用户提供的数据**或**通用学术知识**进行论述。
"""

    # 允许的字数波动范围
    min_words = int(target_words * 0.85)
    max_words = int(target_words * 1.15)
    word_count_strategy = f"""
1.  **目标字数**: **{target_words} 字**。
2.  **强制范围**: 输出内容必须严格控制在 **{min_words} ~ {max_words} 字**之间。

"""
    if is_en_abstract or is_cn_abstract:
        word_count_strategy = "字数遵循摘要标准。"
    # ----------------- 策略F: Python 绘图 -----------------
    visuals_instruction = ""
    
    # 动态图表指令：如果是用户数据，强制可视化
    user_data_chart_instruction = ""
    if has_user_data:
        user_data_chart_instruction = """
        -   **用户数据强制可视化 (Mandatory)**: 
            -   检测到【用户提供的真实数据】。**必须**将该数据转化为可视化的**表格**或**Python统计图**。
            -   **严禁**仅仅在正文中用文字罗列数字，必须配合图表展示。
            -   如果是时间序列数据 -> 画折线图；如果是占比 -> 画饼图；如果是对比 -> 画柱状图。
        -   **去重检查**: 严禁重复生成相同内容的图表。如果数据已画过，请使用“**如图X所示**”引用并分析。
        -  **数据源拓展**: 
                -   **优先**: 使用【用户提供的真实数据】。
                -   **补充**: 如果用户数据不足以支撑当前论点（如维度不够、时间跨度不足），**立即使用【联网检索补充数据】**进行绘图，不要强行复用不相关的用户数据。
"""

    if needs_charts:
        visuals_instruction = f"""
### **策略F: 图表与数据可视化 (Python & Tables)**
**本章节必须包含图表**。{user_data_chart_instruction}
请按以下规范生成：
**决策规则 (Decision Rules) - 严禁冗余**:
1.  **二选一原则**: 针对同一组数据，**只能**选择“Markdown表格”**或者**“Python统计图”其中一种形式，**严禁**对同一数据既画图又制表。
    -   **选表格**: 当数据需要展示精确数值、或者包含大量文字分类时。
    -   **选画图**: 当数据侧重于展示**趋势**（折线图）、**对比**（柱状图）或**占比**（饼图）时。

2.  **表格**:
    -   使用 Markdown 表格语法绘制三线表。
    -   **表名**: 在表格**上方**，格式：`**表{chapter_num}.X 表名**`。

3.  **统计图 (Python Matplotlib) - 核心要求**:
    -   请编写一段**标准、无错、可直接运行的 Python 代码**。
    -   **代码块格式**: 使用 ` ```python ` 包裹。
    -   **关键要求 (CRITICAL)**: 
        -   **数据一致性 (最高优先级)**: 图表数据必须**严格来源于正文论述**。严禁正文说“增长20%”而图表显示“增长50%”。图表是正文数据的“镜像”，**绝对禁止**捏造与正文无关的数据集。
        -   **统计图选型规范**: 必须根据数据逻辑选择最标准的统计图：
            -   **趋势分析** (随时间变化) -> **折线图 (Line Chart)**
            -   **不同项对比** (大小比较) -> **柱状图 (Bar Chart)**
            -   **结构占比** (份额分析) -> **饼图 (Pie Chart)** 或 **环形图**
            -   **相关性/分布** -> **散点图 (Scatter)** 或 **箱线图 (Boxplot)**
            -   *严禁使用非统计学的“示意图”或无意义的图形。*
        -   **库导入**: 必须在代码开头显式导入：`import matplotlib.pyplot as plt`, `import seaborn as sns`, `import pandas as pd`, `import numpy as np`。
        -   **数据自包含**: 数据必须在代码内部完整定义（使用 DataFrame 或字典），**严禁**读取外部文件。
        -   **格式规范**: 严禁使用全角空格（\\u3000）或不间断空格（NBSP），必须使用标准空格缩进。
        -   **字体设置**: 必须包含 `plt.rcParams['font.sans-serif'] = ['SimHei']`,  `font = FontProperties(fname=r'C:\Windows\Fonts\simhei.ttf', size=12)`, `plt.rcParams['axes.unicode_minus'] = False`, 解决中文乱码，并且每个文本元素显式指定字体。
        -   **美观性**: 使用 `sns.set_theme(style="whitegrid")`，配色需符合学术规范（如深蓝、深红、灰度），避免过于花哨。
        -   **输出**: 最后**不需要** `plt.show()`。
    -   **图名**: 在代码块**下方**，格式：`**图{chapter_num}.X 图名**`。

4.  **图文互动**: 
    -   正文论述数据时，必须提及 “**如图{chapter_num}.X所示**” 或 “**如表{chapter_num}.X所示**”。
    -   图表生成后，必须在正文中对图表反映的**趋势、拐点或异常值**进行简要分析，实现图文互证。
"""
    else:
        visuals_instruction = "### **策略F: 图表禁令**\n**严禁生成任何图表。**"

    return f"""
# 角色
你现在扮演一位**严谨的学术导师**，辅助学生撰写毕业论文。
任务：严格遵循特定的写作模板，保证学术规范，**绝不夸大成果**，**图文并茂**。

### **策略A: 格式与排版**
1.  **段落缩进**: **所有段落开头必须包含两个全角空格（　　）**。
2.  **禁用列表**: 严禁使用 Markdown 列表，必须写成连贯段落（研究方法除外）。

### **策略B: 数据与谦抑性 (CRITICAL)**
1.  **字体规范**: **所有数字、字母、标点必须使用半角字符 (Half-width)**。
2.  **数据优先级**: 
    -   **最高优先级**: 如果输入中包含【用户提供的真实数据】，必须**无条件基于该数据**进行分析与制图，**严禁篡改数值**。
    -   **次级来源**: 仅在用户未提供数据时，才使用【联网检索事实】或通用学术知识。
3.  **严禁夸大**: 
    -   **禁止**: “填补空白”、“国内首创”、“完美解决”。
    -   **必须用**: “丰富了...视角”、“提供了实证参考”、“优化了...”。
4.  **严禁捏造**: 无论是用户数据还是检索数据，都必须保持逻辑自洽，严禁凭空杜撰实验结果。
5.  **文件引用**: **严禁编造《》内的政策/文件/著作名称**。必须确保该政策/文件/著作，在真实世界存在且名称完全准确。如果不确定真实全称，**严禁使用书名号**，仅描述其内容即可。
6.  **去AI化表达 (核心指令 - 必须执行)**:
    -   **绝对禁止**: 正文论述中**严禁出现**“**根据提供的数据**”、“**根据输入**”、“**综上所述**”、“**总而言之**”、“**通过上述分析**”等明显的AI或机械化总结词汇。
    -   **强制替换**:
        -   凡是想说“根据提供的数据”时 -> **必须替换为**：“**据有关数据表明**”、“**数据分析显示**”、“**实证结果指出**”、“**调研发现**”或“**统计数据显示**”。
        -   凡是想说“综上所述”时 -> **必须替换为**：“**由此可见**”、“**这一现象反映了**”、“**研究表明**”或直接陈述结论，增强学术沉浸感。

### **策略C: 章节专属逻辑**
{section_rule}

{ref_instruction}

{visuals_instruction}

### **策略E: 字数控制**
{word_count_strategy}
**扩写技巧**: 如果字数不足，请对核心概念进行定义扩展，或增加“举例说明”、“对比分析”、“理论支撑”等环节，**严禁**通过重复废话凑字数。

### **策略G: 结构与边界控制 (CRITICAL - 绝对禁止项)**
1.  **禁止自拟标题**: 输出内容**严禁包含**任何 Markdown 标题符号（#、##、###）。
    -   错误示例：`### 1.1 背景分析`
    -   正确操作：直接开始写背景分析的**正文段落**。
2.  **禁止越界**: **严禁**撰写下一个章节的内容。只关注当前章节：**“{current_chapter_title}”**。
3.  **禁止分点**: 除非是“研究方法”章节，否则严禁使用 `1.` `2.` 或 `*` 进行罗列。使用学术逻辑连接词，例如：“值得注意的是”、“与此同时”、“进一步分析表明”、“从...角度来看”、“由此推导”等，或通过因果逻辑自然衔接。
4.  **严禁元数据标识**: 
    -   **绝对禁止**在正文中输出“(空两格)”、“(接上文)”、“(此处插入...)”等括号说明文字。
    -   **禁止**使用省略号(...)作为段落开头。直接开始论述即可。

### **策略H: 全局视野与定位 (Global Structure)**
为了保证逻辑连贯，请参考以下的**全文大纲**，明确你当前的写作位置.
{full_outline}


请开始写作。
"""

def get_word_distribution_prompt(total_words: int, outline_text: str) -> str:
    return f"""
# 角色
你是一位经验丰富的学术论文编辑。

# 任务
根据用户提供的论文大纲，进行两项规划：
1. **字数分配**: 将总字数 **{total_words}字** 合理分配给各章节。
2. **数据策略**: 判断该章节是否需要**真实数据支撑**（包括用户上传的数据或联网搜索的宏观数据）。

# 规划原则
1. **字数权重**:
   - 核心章节 (实证/分析/设计) 占 60%-70%。
   - 次要章节 (综述/理论) 占 20%-30%。
   - 辅助章节 (摘要/结论) 占 10%-15%。
   - **总字数约束**: 所有章节分配的字数加起来，必须**严格等于 {total_words}**。

2. **数据策略 (needs_data 判定)**:
   - **True (需要数据)**: 章节标题包含“现状”、“分析”、“实证”、“统计”、“调研”、“应用”、“对比”、“实验”、“结果”等词汇，或涉及具体行业背景描述。
   - **False (纯理论)**: 章节标题为“绪论”、“定义”、“概念”、“理论基础”、“研究方法”、“文献综述”、“结论”、“致谢”。

# 待规划大纲
{outline_text}

# 输出格式 (JSON Only)
请直接输出一个 JSON 对象。
Key 是章节的**完整标题**。
Value 是一个对象，包含 `words` (整数) 和 `needs_data` (布尔值)。

**严禁**包含 Markdown 标记，**严禁**废话。

示例格式：
{{
    "1.1 研究背景": {{ "words": 400, "needs_data": true }},
    "1.2 核心概念界定": {{ "words": 300, "needs_data": false }},
    "3.1 市场现状分析": {{ "words": 800, "needs_data": true }}
}}
"""

class PaperAutoWriter:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        # 主线程客户端
        self.main_client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)

    # --------------------------------------------------------------------------
    # 辅助方法：Client 隔离调用
    # --------------------------------------------------------------------------
    
    def _call_llm_with_client(self, client, system_prompt: str, user_prompt: str) -> str:
        """[基础方法] 使用指定的 client 实例调用 LLM"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    temperature=0.7, 
                    stream=False
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"⚠️ [LLM Error] Attempt {attempt+1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    raise e # 抛出异常让上层捕获

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """[主线程] 调用方法"""
        return self._call_llm_with_client(self.main_client, system_prompt, user_prompt)

    # --------------------------------------------------------------------------
    # 联网搜索方法
    # --------------------------------------------------------------------------
    
    def _research_phase_with_client(self, client, topic: str) -> str:
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "严谨数据分析师。列出关于主题的真实数据、政策。"},
                    {"role": "user", "content": f"检索关于'{topic}'的真实事实："}
                ],
                temperature=0.3, stream=False
            )
            return response.choices[0].message.content.strip()
        except: 
            return ""

    def _research_phase(self, topic: str) -> str:
        return self._research_phase_with_client(self.main_client, topic)

    # --------------------------------------------------------------------------
    # 状态检查
    # --------------------------------------------------------------------------

    def _check_process_status(self, check_status_func) -> bool:
        while check_status_func() == "paused":
            time.sleep(1)
        return check_status_func() == "stopped"

    def _extract_chapter_num(self, title: str) -> str:
        match = re.match(r'^(\d+)', title.strip())
        return match.group(1) if match else ""

    def _determine_header_prefix(self, chapter: Dict, sec_title: str) -> str:
        level = 2
        if 'level' in chapter: level = int(chapter['level']) + 1
        return "#" * min(max(level, 2), 6)

    def _clean_and_format(self, raw_content: str, sec_title: str, ref_manager) -> str:
        if "摘要" in sec_title or "Abstract" in sec_title:
            raw_content = re.sub(r'^#+\s*(摘要|Abstract)\s*', '', raw_content, flags=re.IGNORECASE).strip()
        
        dirty_patterns = [r'[\(（]接上文[\)）]', r'[\(（]空两格[\)）]', r'^\.\.\.', r'接上文：']
        for p in dirty_patterns:
            raw_content = re.sub(p, '', raw_content)

        if ref_manager:
            raw_content = ref_manager.process_text_deterministic(raw_content)
        
        processed = TextCleaner.convert_cn_numbers(raw_content)
        lines = []
        for line in processed.split('\n'):
            line = line.strip()
            if (line and not line.startswith('　　') and not line.startswith('#') and 
                not line.startswith('|') and not line.startswith('```') and "import" not in line):
                line = '　　' + line 
            lines.append(line)
        return '\n\n'.join(lines)

    def _refine_content(self, raw_content: str, target: int, sec_title: str, sys_prompt: str, user_prompt: str) -> Generator[str, None, str]:
        content_no_code = re.sub(r'```[\s\S]*?```', '', raw_content)
        current_len = len(re.sub(r'\s', '', content_no_code))
        if target < 300: return raw_content
        
        # 简化版精简逻辑，防止递归报错
        return raw_content

    # --------------------------------------------------------------------------
    # [核心修复] 单章节处理函数 (增加详细Debug Log)
    # --------------------------------------------------------------------------
    
    def _process_single_chapter(self, task_bundle):
        """线程工作函数"""
        i = -1
        sec_title = "未知章节"
        logs = []
        
        try:
            if len(task_bundle) < 12: 
                return { "index": -1, "type": "error", "msg": f"参数不足: {len(task_bundle)}", "logs": [] }

            (api_key, base_url, model, task_id, title, chapter, 
             ref_domestic, ref_foreign,  # <--- 这里接收分开的文献
             custom_data, context_summary, index_val, 
             full_outline_str) = task_bundle
            
            i = index_val
            sec_title = chapter.get('title', '无标题')
            target = int(chapter.get('words', 500))
            is_parent = chapter.get('is_parent', False)

            # Debug Print
            # print(f"[Thread {i}] 处理章节: {sec_title} | 字数: {target}")

            # 2. 标题处理 (父节点直接返回)
            header_prefix = self._determine_header_prefix(chapter, sec_title)
            if is_parent or target <= 0:
                return {
                    "index": i, "type": "header_only", 
                    "content": f"{header_prefix} {sec_title}\n\n",
                    "logs": [f"生成标题: {sec_title}"]
                }

            # 3. 初始化 Client
            local_client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
            
            chapter_num = self._extract_chapter_num(sec_title)
            logs.append(f"🚀 [并发启动] 正在撰写: {sec_title}")

            # 4. 数据上下文准备
            facts_context = ""
            use_data_flag = chapter.get('use_data', False)
            has_user_data = False
            
            if "摘要" not in sec_title and use_data_flag:
                if custom_data and len(custom_data.strip()) > 5:
                    cleaned_data = TextCleaner.convert_cn_numbers(custom_data)
                    facts_context += f"\n【用户真实数据】:\n{cleaned_data}\n"
                    has_user_data = True
                
                # logs.append(f"   - 🔍 [并行检索] 补充数据...")
                facts = self._research_phase_with_client(local_client, f"{title} - {sec_title} 数据")
                if facts:
                    facts_context += f"\n【联网补充数据】:\n{facts}\n"

            # [修改] 5. 智能文献选择逻辑
            target_ref_list = []
            
            # 判断逻辑：根据标题关键词锁定文献库
            is_domestic_review = "国内" in sec_title and ("现状" in sec_title or "综述" in sec_title)
            is_foreign_review = "国外" in sec_title and ("现状" in sec_title or "综述" in sec_title)
            
            raw_ref_text = ""

            if is_domestic_review:
                logs.append(f"   - 📚 锁定：国内参考文献")
                raw_ref_text = ref_domestic
            elif is_foreign_review:
                logs.append(f"   - 📚 锁定：国外参考文献")
                raw_ref_text = ref_foreign
            else:
                # 其他章节（如理论、正文），为了引用丰富度，合并两者
                # 中间加换行符防止粘连
                raw_ref_text = f"{ref_domestic}\n{ref_foreign}"

            # 解析为列表 (取前8条，防止 Token 爆炸)
            if raw_ref_text:
                target_ref_list = [line.strip() for line in raw_ref_text.split('\n') if line.strip()][:8]

            # 6. Prompt 构建
            sys_prompt = get_academic_thesis_prompt(
                target, 
                target_ref_list, # 传入筛选后的列表
                sec_title, 
                chapter_num, 
                has_user_data, 
                full_outline=full_outline_str
            )
            user_prompt = f"题目：{title}\n章节：{sec_title}\n前文摘要：{context_summary}\n【重要约束】目标字数：{target}字\n{facts_context}"

            # 7. LLM 调用
            raw_content = self._call_llm_with_client(local_client, sys_prompt, user_prompt)

            # 8. 简单字数检查与扩写 (省略详细逻辑，保持原有即可)
            content_no_code = re.sub(r'```[\s\S]*?```', '', raw_content)
            current_len = len(re.sub(r'\s', '', content_no_code))
            if "摘要" not in sec_title and target > 300 and current_len < target * 0.5:
                 try:
                    raw_content = self._call_llm_with_client(local_client, sys_prompt, user_prompt + "\n\n请大幅扩写，增加细节。")
                 except: pass

            # 9. 清洗
            # 这里的 ref_manager 传 None 即可，因为我们在 Prompt 里已经处理了引用格式
            final_content = self._clean_and_format(raw_content, sec_title, None)
            section_md = f"{header_prefix} {sec_title}\n\n{final_content}\n\n"
            
            return {
                "index": i, "type": "content", 
                "content": section_md, "raw_text": final_content, "logs": logs
            }

        except Exception as e:
            err_msg = f"❌ {sec_title} 异常: {str(e)}"
            print(f"[Thread {i}] ERROR: {err_msg}")
            return { "index": i, "type": "error", "msg": str(e), "logs": [err_msg] }

    # --------------------------------------------------------------------------
    # 并发生成器
    # --------------------------------------------------------------------------
    def _format_outline(self, chapters: List[Dict]) -> str:
        outline_lines = []
        for ch in chapters:
            title = ch.get('title', '未命名')
            outline_lines.append(f"- {title}")
        return "\n".join(outline_lines)

    def generate_stream(self, task_id: str, title: str, chapters: List[Dict], ref_domestic: str, ref_foreign: str, custom_data: str, check_status_func, initial_context: str = "") -> Generator[str, None, None]:
        
        # 这里的 ref_manager 主要用于最后生成文末的参考文献列表，所以合并两者
        combined_refs = f"{ref_domestic}\n{ref_foreign}"
        ref_manager = ReferenceManager(combined_refs)
        
        yield f"data: {json.dumps({'type': 'log', 'msg': '🚀 启动高并发生成引擎 (Max Threads=8)...'})}\n\n"
        
        full_content = f"# {title}\n\n"
        global_context = initial_context if initial_context else f"论文题目：《{title}》"
        
        # 预先生成全文大纲文本字符串
        full_outline_str = self._format_outline(chapters)

        MAX_WORKERS = 8
        all_futures = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # 1. 提交任务
            for i, chapter in enumerate(chapters):
                if self._check_process_status(check_status_func): break
                
                task_bundle = (
                    self.api_key, self.base_url, self.model,
                    task_id, title, chapter, 
                    ref_domestic, ref_foreign,  # <--- 新增的两个参数
                    custom_data, global_context[:800], i,
                    full_outline_str
                )
                future = executor.submit(self._process_single_chapter, task_bundle)
                all_futures.append(future)
            
            # 2. 获取结果
            for future in all_futures:
                if self._check_process_status(check_status_func):
                    executor.shutdown(wait=False)
                    break
                
                while True:
                    try:
                        result = future.result(timeout=1)
                        for log in result.get('logs', []):
                            yield f"data: {json.dumps({'type': 'log', 'msg': log})}\n\n"
                        
                        if result['type'] == 'error':
                            yield f"data: {json.dumps({'type': 'log', 'msg': result['msg']})}\n\n"
                            break

                        if result['type'] in ['content', 'header_only']:
                            content_md = result['content']
                            full_content += content_md
                            yield f"data: {json.dumps({'type': 'content', 'md': content_md})}\n\n"
                            global_context += result.get('raw_text', '')[-200:]
                        
                        break
                    except concurrent.futures.TimeoutError:
                        yield f": keep-alive\n\n"
                        if self._check_process_status(check_status_func): return
                    except Exception as e:
                        yield f"data: {json.dumps({'type': 'log', 'msg': f'❌ 主线程异常: {str(e)}'})}\n\n"
                        break

        if check_status_func() != "stopped":
            # 生成文末参考文献列表
            bib = ref_manager.generate_bibliography()
            full_content += bib
            yield f"data: {json.dumps({'type': 'content', 'md': bib})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

    # --------------------------------------------------------------------------
    # 其他公共方法
    # --------------------------------------------------------------------------

    def rewrite_chapter(self, title: str, section_title: str, user_instruction: str, context: str, custom_data: str, original_content: str = "") -> str:
        sys_prompt = get_rewrite_prompt(title, section_title, user_instruction, context[-800:], custom_data, original_content)
        user_prompt = f"论文题目：{title}\n请修改章节：{section_title}\n用户的具体修改意见：{user_instruction}"
        return self._call_llm(sys_prompt, user_prompt)
    
    def plan_word_count(self, total_words: int, outline_list: List[str]) -> Dict[str, Dict]:
        outline_str = "\n".join(outline_list)
        prompt = get_word_distribution_prompt(total_words, outline_str)
        
        try:
            response = self.main_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是一个严格输出 JSON 的学术规划师。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                stream=False,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```"): content = re.sub(r'```json|```', '', content).strip()
            
            try:
                raw_map = json.loads(content)
            except json.JSONDecodeError:
                return {}

            standardized_map = {}
            for k, v in raw_map.items():
                if "total" in k.lower(): continue
                if isinstance(v, dict):
                    w = int(v.get('words', 0))
                    d = v.get('needs_data', False)
                    if isinstance(d, str): d = d.lower() == 'true'
                    standardized_map[k] = {"words": w, "needs_data": d}
                elif isinstance(v, (int, float)):
                    standardized_map[k] = {"words": int(v), "needs_data": False}
            
            current_total = sum(item['words'] for item in standardized_map.values())
            if current_total == 0: return standardized_map

            ratio = total_words / current_total
            final_map = {}
            for k, v in standardized_map.items():
                final_map[k] = {"words": int(v['words'] * ratio), "needs_data": v['needs_data']}
            
            # 误差修正
            new_total = sum(item['words'] for item in final_map.values())
            diff = total_words - new_total
            if diff != 0 and final_map:
                max_key = max(final_map, key=lambda k: final_map[k]['words'])
                final_map[max_key]['words'] += diff
                
            return final_map
        except Exception as e:
            print(f"Plan error: {e}")
            return {}