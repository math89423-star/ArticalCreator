import re
import json
import time
from typing import List, Dict, Generator
from openai import OpenAI
from typing import Dict, Generator
from .reference import ReferenceManager
from .word import TextCleaner


def get_academic_thesis_prompt(target_words: int, ref_content_list: List[str], current_chapter_title: str, chapter_num: str, has_user_data: bool = False) -> str:
    
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
    elif any(k in current_chapter_title for k in ["现状", "综述", "Review"]):
        if ref_content_list:
            first_ref = ref_content_list[0]
            if len(ref_content_list) > 1:
                other_refs_prompt = "\n".join([f"{{文献{i+2}}}: {ref}" for i, ref in enumerate(ref_content_list[1:])])
            else:
                other_refs_prompt = "无后续文献"
            
            section_rule = f"""
**当前任务：撰写研究现状 (文献综述)**
**核心目标**：将提供的参考文献列表转化为逻辑通顺的学术评述。

### **引用规范 (零容忍规则)**
1.  **禁止出现ID**: 正文中**绝对禁止**出现 "参考文献ID"、"文献1"、"Reference ID" 等字样。
2.  **引用格式**: 必须从文献内容中提取**作者**和**年份**，格式为 `作者(年份)`。
    -   *例*: "Zhang (2023) 提出了..." 或 "OpenAI (2024) 发布了..."
    -   *如果找不到作者*: 使用 `《标题》(年份)`。
3.  **禁止模糊**: 严禁使用 "某学者"、"有研究"、"该作品" 等指代不明的词，**必须指名道姓**。
4.  **顺序与频次**: 
    -   必须**严格按照列表顺序**逐一论述。
    -   列表中的**每一条**文献都必须被引用**一次且仅一次**。
    -   每段论述结束句末尾必须加 `[REF]` 标记。

### **写作逻辑**
1.  **第一段 (导语)**: 简要概括该领域的总体发展趋势（约80字）。
2.  **第二段 (核心综述)**: 
    -   **首条详述**: 针对 **{{文献1}}** ({first_ref}) 进行详细评述（约150字）。写明：作者+年份+核心贡献+局限性。文末加 `[REF]`。
    -   **后续串联**: 依次对 **{{文献2}}** 及后续文献进行评述。
        -   *必须从提供的文本中提取真实作者和观点，严禁编造。*
        -   使用连接词（如"与之类似"、"然而"、"在此基础上"）将不同文献逻辑串联。
        -   格式：`作者(年份) + 观点/方法 + [REF]`。
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

    word_count_strategy = f"目标: **{target_words} 字**。请务必**一次性完成指定的字数保障不过多超出**，" 
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

请开始写作。
"""


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
        except: 
            return ""

    def _extract_chapter_num(self, title: str) -> str:
        match_digit = re.match(r'^(\d+)', title.strip())
        if match_digit: return match_digit.group(1)
        match_cn = re.match(r'^第([一二三四五六七八九十]+)[章|部分]', title.strip())
        if match_cn:
            cn_map = {'一':'1','二':'2','三':'3','四':'4','五':'5','六':'6','七':'7','八':'8','九':'9','十':'10'}
            return cn_map.get(match_cn.group(1), "")
        return ""

    def _check_process_status(self, check_status_func) -> bool:
        """检查任务状态：处理暂停，返回是否停止"""
        while check_status_func() == "paused":
            time.sleep(1)
        return check_status_func() == "stopped"

    def _determine_header_prefix(self, chapter: Dict, sec_title: str) -> str:
        """计算 Markdown 标题层级前缀 (##, ###, etc.)"""
        header_level = 2
        # 如果前端传递了层级，直接使用
        if 'level' in chapter:
            header_level = int(chapter['level']) + 1
        else:
            # 兼容旧逻辑：根据点号智能猜测
            parts = sec_title.split('.')
            if len(parts) >= 3: header_level = 4
            elif len(parts) == 2: header_level = 3
            else: header_level = 3 # 默认小节是三级
        
        # 限制层级范围
        header_level = min(max(header_level, 2), 6)
        return "#" * header_level

    def _get_facts_context(self, chapter: Dict, title: str, sec_title: str, custom_data: str) -> Generator[str, None, str]:
        """获取事实数据上下文 (Yields logs, returns context string)"""
        facts_context = ""
        use_data_flag = chapter.get('use_data', False)

        # 仅对非摘要、非结论章节，且【开关开启】时，才启用数据挂载
        #                 ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
        if "摘要" not in sec_title and "结论" not in sec_title and use_data_flag:
            
            # 1. 挂载用户数据
            if custom_data and len(custom_data.strip()) > 5:
                yield json.dumps({'type': 'log', 'msg': f'   - [已启用] 挂载用户真实数据...'})
                cleaned_data = TextCleaner.convert_cn_numbers(custom_data)
                facts_context += f"\n【用户提供的真实数据 (最高优先级)】:\n{cleaned_data}\n"
            
            # 2. 强制联网补充数据 (双轨制：有用户数据也搜，没用户数据也搜)
            yield json.dumps({'type': 'log', 'msg': f'   - [补充] 正在联网检索更多数据以丰富论点...'})
            facts = self._research_phase(f"{title} - {sec_title} 统计数据 现状分析")
            if facts:
                facts = TextCleaner.convert_cn_numbers(facts)
                facts_context += f"\n【联网检索补充数据 (当用户数据不足时使用)】:\n{facts}\n"
                
            facts_context += "\n请综合使用上述数据。如果用户数据已在之前章节使用过，请优先使用联网补充数据进行新的图表制作。"
        
        return facts_context

    def _refine_content(self, raw_content: str, target: int, sec_title: str, sys_prompt: str, user_prompt: str) -> Generator[str, None, str]:
        """智能扩写/精简逻辑 (Yields logs, returns refined content)"""
        current_len = len(re.sub(r'\s', '', raw_content))

        if target < 300:
            return raw_content
        
        # 摘要章节不进行字数优化
        if "摘要" not in sec_title and "Abstract" not in sec_title:
            # 扩写逻辑
            if current_len < target * 0.4:
                yield json.dumps({'type': 'log', 'msg': f'   - 字数优化: 正在扩充内容 ({current_len}/{target})...'})
                expand_prompt = (
                    f"当前字数({current_len})与目标({target})差距较大。\n"
                    f"请**扩写**上述内容。红线要求：\n"
                    f"1. **严禁**删除原文中的任何 `[REF]` 引用标记。\n"
                    f"2. 增加具体案例、理论分析或数据对比。\n"
                    f"3. **严禁**输出“好的”、“扩写如下”等废话，直接输出扩写后的正文。\n"
                )
                try:
                    resp = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_prompt},
                            {"role": "assistant", "content": raw_content},
                            {"role": "user", "content": expand_prompt}
                        ],
                        temperature=0.7
                    )
                    return resp.choices[0].message.content.strip()
                except Exception as e:
                    print(f"扩写失败: {e}")
            
            # 精简逻辑
            elif current_len > target * 2.5:
                yield json.dumps({'type': 'log', 'msg': f'   - 字数优化: 正在精简内容 ({current_len}/{target})...'})
                condense_prompt = (
                    f"当前字数({current_len})远超目标({target})。\n"
                    f"请**精简**上述内容。红线要求：\n"
                    f"1. **必须保留所有 `[REF]` 引用标记**，绝对不能删减参考文献。\n"
                    f"2. 删除重复的形容词，保留核心论点。\n"
                    f"3. **严禁**输出“好的”等废话，直接输出结果。\n"
                )
                try:
                    resp = self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": sys_prompt},
                            {"role": "user", "content": user_prompt},
                            {"role": "assistant", "content": raw_content},
                            {"role": "user", "content": condense_prompt}
                        ],
                        temperature=0.7
                    )
                    return resp.choices[0].message.content.strip()
                except Exception as e:
                    print(f"精简失败: {e}")
        
        return raw_content

    def _clean_and_format(self, raw_content: str, sec_title: str, ref_manager) -> str:
        # 1. 摘要标题清洗
        if "摘要" in sec_title or "Abstract" in sec_title:
            raw_content = re.sub(r'^#+\s*(摘要|Abstract)\s*', '', raw_content, flags=re.IGNORECASE).strip()
            if raw_content.startswith("摘要") and len(raw_content) < 10: raw_content = raw_content[2:].strip()
            if raw_content.startswith("Abstract") and len(raw_content) < 15: raw_content = raw_content[8:].strip()

        # [新增] 强力清洗 LLM 的“元数据痕迹” (全局替换，不限于开头)
        # 去除 (接上文), (空两格), (此处...), (本节...)
        dirty_patterns = [
            r'[\(（]接上文[\)）]', r'[\(（]紧接上文[\)）]', 
            r'[\(（]空两格[\)）]', r'[\(（]空格[\)）]', r'[\(（]空两格正文[\)）]',
            r'[\(（]此处.*?[\)）]', # 去除 (此处应补充...)
            r'^接上文[：:,，]',      # 去除开头的 接上文：
            r'^\.\.\.'             # 去除开头的 ...
        ]
        for pattern in dirty_patterns:
            raw_content = re.sub(pattern, '', raw_content, flags=re.IGNORECASE)

        # 2. 通用标题重复清洗
        temp_lines = raw_content.strip().split('\n')
        if temp_lines:
            first_line_core = re.sub(r'[#*\s]', '', temp_lines[0])
            title_core = re.sub(r'[#*\s]', '', sec_title)
            if title_core in first_line_core and len(first_line_core) < len(title_core) + 8:
                raw_content = '\n'.join(temp_lines[1:])

        # 3. 引用处理
        processed_content = ref_manager.process_text_deterministic(raw_content)
        processed_content = TextCleaner.convert_cn_numbers(processed_content)

        # 4. 段落缩进格式化
        lines = processed_content.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            # 二次清洗行首残留
            line = re.sub(r'^[\(（]空两格[\)）]', '', line) 
            
            if (line and not line.startswith('　　') and not line.startswith('#') and 
                not line.startswith('|') and not line.startswith('```') and "import" not in line and "plt." not in line):
                line = '　　' + line 
            formatted_lines.append(line)
        
        return '\n\n'.join(formatted_lines)

    def generate_stream(self, task_id: str, title: str, chapters: List[Dict], references_raw: str, custom_data: str, check_status_func, initial_context: str = "") -> Generator[str, None, None]:
        ref_manager = ReferenceManager(references_raw)
        yield f"data: {json.dumps({'type': 'log', 'msg': '初始化...'})}\n\n"
        chapter_ref_map = ref_manager.distribute_references_smart(chapters)
        
        full_content = f"# {title}\n\n"
        context = initial_context if initial_context else "论文开头"
        
        for i, chapter in enumerate(chapters):
            # 1. 状态检查 (暂停/停止)
            if self._check_process_status(check_status_func):
                yield f"data: {json.dumps({'type': 'log', 'msg': '⚠️ 收到停止指令，正在中断...'})}\n\n"
                break
            
            sec_title = chapter['title']
            
            # 2. 标题层级处理
            header_prefix = self._determine_header_prefix(chapter, sec_title)
            
            # 3. 仅标题处理 (父节点 或 字数<=0)
            target = int(chapter.get('words', 500))
            is_parent = chapter.get('is_parent', False)
            
            if is_parent or target <= 0:
                header_md = f"{header_prefix} {sec_title}\n\n" 
                full_content += header_md
                yield f"data: {json.dumps({'type': 'content', 'md': header_md})}\n\n"
                if not is_parent: # 如果是写作点但字数为0，记录日志
                    yield f"data: {json.dumps({'type': 'log', 'msg': f'生成标题: {sec_title} (跳过正文)'})}\n\n"
                continue

            # 4. 上下文与引用准备
            assigned_refs = chapter_ref_map.get(i, [])
            ref_manager.set_current_chapter_refs(assigned_refs)
            chapter_num = self._extract_chapter_num(sec_title)
            yield f"data: {json.dumps({'type': 'log', 'msg': f'正在撰写: {sec_title}'})}\n\n"

            # 5. 获取数据上下文 (Generator 迭代)
            facts_context = ""
            fact_gen = self._get_facts_context(chapter, title, sec_title, custom_data)
            try:
                while True:
                    val = next(fact_gen)
                    yield f"data: {val}\n\n"
            except StopIteration as e:
                facts_context = e.value

            # 6. [核心修改] 检测是否启用了用户数据
            has_user_data = "用户提供的真实数据" in facts_context

            # 7. 构建 Prompt (传递 has_user_data 参数)
            if "摘要" in sec_title or "Abstract" in sec_title:
                sys_prompt = get_academic_thesis_prompt(target, [r[1] for r in assigned_refs], sec_title, chapter_num, has_user_data)
                user_prompt = f"题目：{title}\n章节：{sec_title}\n要求：请直接输出摘要的正文内容，严禁输出“### 摘要”或“### Abstract”等标题。请严格按照“摘要正文 + 关键词”的格式输出。"
            else:
                sys_prompt = get_academic_thesis_prompt(target, [r[1] for r in assigned_refs], sec_title, chapter_num, has_user_data)
                user_prompt = f"题目：{title}\n章节：{sec_title}\n前文：{context[-600:]}\n字数：{target}\n{facts_context}"

            # 8. 调用 LLM
            raw_content = self._call_llm(sys_prompt, user_prompt)

            # 9. 优化内容 (扩写/精简 Generator 迭代)
            refine_gen = self._refine_content(raw_content, target, sec_title, sys_prompt, user_prompt)
            try:
                while True:
                    val = next(refine_gen)
                    yield f"data: {val}\n\n"
            except StopIteration as e:
                raw_content = e.value

            # 10. 清洗与格式化
            final_content = self._clean_and_format(raw_content, sec_title, ref_manager)

            # 11. 输出结果
            section_md = f"{header_prefix} {sec_title}\n\n{final_content}\n\n"
            full_content += section_md
            context = final_content
            yield f"data: {json.dumps({'type': 'content', 'md': section_md})}\n\n"

        # 结束处理
        if check_status_func() != "stopped":
            bib = ref_manager.generate_bibliography()
            full_content += bib
            yield f"data: {json.dumps({'type': 'content', 'md': bib})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'log', 'msg': '🛑 任务已完全终止 (已跳过后续内容)'})}\n\n"