
from typing import List

def get_academic_thesis_prompt_en(
        target_words: int, 
        ref_content_list: List[str], 
        current_chapter_title: str, 
        chapter_num: str, 
        has_user_data: bool = False, 
        full_outline: str = "",
        opening_report_data: dict = None,
        chart_type: str = 'none'
    ) -> str:
    
    # ------------------------------------------------------------------
    # 1. Section Logic (EN) - Strict Translation of CN Logic
    # ------------------------------------------------------------------
    section_rule = ""
    title_lower = current_chapter_title.lower()
    
    # A. Abstract
    if "abstract" in title_lower:
        section_rule = """
**Current Task: Write English Abstract & Keywords**
**NO Titles**: Do NOT output "### Abstract", start writing the body text directly.

**Logic Structure**:
1. **Background**: Brief background (approx. 50 words).
2. **Methodology**: What was done and what methods were used (approx. 100 words).
3. **Key Findings**: What data or conclusions were obtained (approx. 100 words).
4. **Contribution**: Theoretical value (approx. 50 words).

**Formatting Requirements**:
    - **NO** bullet points (1. 2. 3.). Must be a single, coherent paragraph.
    - End with: **Keywords**: Word1; Word2; Word3; Word4 (3-5 words, separated by semicolons).
"""

    # B. Background & Significance
    elif any(k in title_lower for k in ["introduction", "background"]):
        section_rule = """
**Current Task: Write Research Background**
**Content Requirements**:
1. **Policy/Fact Support**: Must integrate **global trends, national policies, industry reports, or major social events** from the last 3 years.
2. **Real-World Pain Points**: Address specific contradictions or unresolved issues from a macro (Social) or Industry perspective.
3. **Data Sense**: Cite (or logically infer) industry data to enhance persuasion.
4. **Sentence Structure**: Avoid flowery language; every sentence must convey high-density information.
"""
    elif "significance" in title_lower or "importance" in title_lower:
        section_rule = """
**Current Task: Write Research Significance**
**Dimension Breakdown**:
1. **Theoretical Significance**: Do NOT say "filled a gap". Must be phrased as "**Enriched the theoretical research from the perspective of...**", "**Expanded the application boundary of...**", or "**Provided new empirical evidence for...**".
2. **Practical Significance**: Specific guidance for **enterprises, governments, or society** (e.g., "Reduced costs for...", "Improved efficiency of...", "Provided reference for decision-making").
"""

    # C. Literature Review
    elif any(k in title_lower for k in ["review", "literature", "related work", "status"]):
        if ref_content_list:
            first_ref = ref_content_list[0]
            other_refs_prompt = "\n".join([f"{{Ref {i+2}}}: {ref}" for i, ref in enumerate(ref_content_list[1:])]) if len(ref_content_list) > 1 else "No further refs"
            
            section_rule = f"""
**Current Task: Write Literature Review**
**Core Goal**: Convert the provided reference list into a logical academic review.
**Structure: Total-Part-Total**
1. **Para 1 (Overview)**: Briefly summarize current research hotspots (approx. 100 words), leading into specific studies.
2. **Para 2 (Core Review - Part)**:
   - **First Detail**: Detailed review of **{{Ref 1}}** ({first_ref}) (approx. 200 words). Format: **Author (Year) argues/points out... [REF]**.
   - **Subsequent Links**: Review subsequent references in order. **MUST use logical connectors** (e.g., "In contrast,", "Furthermore,", "Building on this,") to connect them. **NO simple listing**.
3. **Para 3 (Summary/Gap - Total)**: Summarize commonalities, point out **limitations or controversies**, and introduce the focus of this study.

**Citation Rules**:
1. **NO IDs**: Do NOT output "Ref ID" or "Ref 1" in the text.
2. **Format**: Extract **Author** and **Year**. Format: `Author (Year)`.
   - *Example*: "Smith (2025) argues that..."
3. **NO Ambiguity**: Do NOT use "Some scholars" or "A study"; **Name specific authors**.
4. **Order**: Must follow the list order strictly.

**References to Review**:
- {{Ref 1}}: {first_ref}
{other_refs_prompt}
"""
        else:
            section_rule = "**Current Task: Write Literature Review**\nWrite based on general academic knowledge. Maintain Total-Part-Total structure. Cite real classic studies."

    # D. Literature Critique / Gap Analysis
    elif "critique" in title_lower or "gap" in title_lower or "comment" in title_lower:
        section_rule = """
**Current Task: Write Literature Comments (Gap Analysis)**
**Logic**:
1. **Summary**: "Through the above literature review, this study finds..."
2. **Affirmation**: Existing research has achieved rich results in...
3. **Gap Analysis**: "However, there are still shortages in..." or "Few studies combine X with Y...".
4. **Positioning**: "Therefore, based on existing research, this paper will focus on...".
**Requirement**: This is a transitional paragraph (300-400 words). **No specific citations needed**.
"""

    # E. Research Content (Outline Description)
    elif "content" in title_lower and "method" not in title_lower:
        section_rule = """
**Current Task: Write Research Content Overview**
**Core Goal**: Elaborate on the research work chapter by chapter following the logical flow (Problem-Analysis-Solution).
**Structure**: Use **Paragraphs**, **NO Lists**. 5-6 paragraphs recommended.

**Detailed Guide & Template**:
1. **Para 1 (Overview)**: Summarize the main theme and core logic.
   - *Example*: "This study focuses on... following the logic of 'Theory-Status-Empirical-Strategy'..."
2. **Para 2 (Basics - Ch 1-2)**: Cover introduction and theoretical basis.
   - *Example*: "**Chapter 1** is the introduction... **Chapter 2** defines core concepts and reviews... theories..."
3. **Para 3 (Status/Problem - Ch 3)**: Focus on status description and problem identification.
   - *Example*: "**Chapter 3** focuses on the status analysis of... identifying key problems such as..."
4. **Para 4 (Core Analysis - Ch 4)**: **Focus Point**. Describe models, data, and verification.
   - *Example*: "**Chapter 4** is the core. It constructs a ... model, uses ... methods to empirically test the relationship between..."
5. **Para 5 (Strategy/Conclusion - Ch 5-6)**: Solutions and summary.
   - *Example*: "**Chapter 5** proposes optimization strategies for... **Chapter 6** summarizes the conclusions..."
"""

    # F. Methodology
    elif any(k in title_lower for k in ["method", "methodology", "design"]):
        section_rule = """
**Current Task: Write Research Methodology**
**Core Goal**: Clearly explain the specific methods, steps, and applicability. Ensure reproducibility.
**Structure**: Use **Bullet Points** (1. 2. 3.). Select 2-3 core methods.

**Detailed Guide & Templates**:

1. **Literature Research Method (Mandatory)**:
   - *Key Points*: Data sources (Databases), keywords, and how they are used.
   - *Template*: "**1. Literature Research Method**. This study collected literature from authoritative databases like Web of Science/Google Scholar using keywords such as '...'. It systematically reviewed the theoretical basis..."

2. **Empirical Analysis Method (For Quantitative)**:
   - *Key Points*: Data source, software (SPSS/Stata/Python), and specific analysis (Regression/Correlation).
   - *Template*: "**2. Empirical Analysis Method**. This paper selected ... as the sample. Using Stata/SPSS software, it constructed a ... model to empirically test the relationship between..."

3. **Case Study Method (For Qualitative/Management)**:
   - *Key Points*: Reason for selection (Typicality) and analysis logic.
   - *Template*: "**3. Case Study Method**. This paper selected ... as a representative case. By collecting data/interview materials, it deeply analyzed the practices and problems..."

4. **Questionnaire Survey Method (For Survey)**:
   - *Key Points*: Design basis, distribution, recovery rate, reliability/validity test.
   - *Template*: "**4. Questionnaire Survey Method**. Based on the ... scale, a questionnaire was designed and distributed to... A total of ... valid questionnaires were recovered. Reliability and validity tests ensured data quality."

**Key Requirements**:
- **No Empty Definitions**: Do NOT write "Literature method is defined as...". Write **"How it is done in THIS study"**.
- **Software & Data**: Mention specific tools (SPSS, Python, etc.) if applicable.
"""

    # G. Theoretical Basis
    elif "theory" in title_lower or "concept" in title_lower or "basis" in title_lower:
        section_rule = """
**Current Task: Write Concepts and Theoretical Basis**
**Requirements**:
1. **Concepts**: Define 2 core keywords.
2. **Theories**: Select 1-2 classic theories related to the topic (e.g., PEST, 4P, SWOT, TAM, Maslow).
3. **Relevance**: **Strictly Forbidden** to just pile up definitions. Must explain **how the theory guides this study** (e.g., "This study will analyze ... behavior based on ... theory").
"""

    # H. Conclusion
    elif "conclusion" in title_lower:
        section_rule = """
**Current Task: Write Conclusion**
**Structure**:
1. **Major Findings**: "Through ... methods, this study concludes: ..." (Summarize core points).
2. **Innovations**: Briefly describe the uniqueness of this paper.
3. **Limitations & Outlook**: Honestly state limitations in sample/time/method and propose future directions.
**Tone**: Affirmative, objective. Avoid ambiguity.
"""

    # I. General Body
    else:
        section_rule = """
**Current Task: Write Body Analysis**
1. **Logic Driven**: The core is the analytical train of thought.
2. **Deep Argumentation**: Each paragraph must have a Point, Evidence (Data/Theory), and Conclusion.
"""

    # ------------------------------------------------------------------
    # 2. Citation Instruction (EN)
    # ------------------------------------------------------------------
    ref_instruction = ""
    is_review_chapter = any(k in title_lower for k in ["review", "literature", "related", "status"])
    
    if ref_content_list and is_review_chapter:
        ref_instruction = f"""
### **Strategy D: Citation Execution**
This section **MUST** cite the assigned references.
1. **Format**: When mentioning a point, use specific numbers like `[1]`, `[2]` corresponding to the list order.
   - *Wrong*: Smith says...[REF]
   - *Right*: Smith (2023) points out...[1]
2. **No Placeholders**: **Absolutely Forbidden** to output `[REF]` or `[Reference]`.
3. **Quantity**: You must insert {len(ref_content_list)} citation markers.
4. **Connection**: Even if not perfectly relevant, use connectors like "Furthermore, studies from the perspective of... point out" to force a logical loop.
"""
    else:
        ref_instruction = """
### **Strategy D: Citation Ban**
**Do NOT use the reference list in this section.**
1. **Absolutely Forbidden** to use `[REF]`, `[1]` markers.
2. **Absolutely Forbidden** to use phrases like "Literature [x]" or "Some scholars point out".
3. Base your arguments entirely on **theoretical deduction**, **user-provided data**, or **general academic knowledge**.
"""

    # ------------------------------------------------------------------
    # 3. Word Count Strategy (EN)
    # ------------------------------------------------------------------
    min_words = int(target_words * 0.75)
    max_words = int(target_words * 1.25)
    word_count_strategy = f"""
### **Strategy E: Word Count Control**
1. **Target**: **{target_words} words**.
2. **Range**: Output must be between **{min_words} ~ {max_words} words**.
"""
    if "abstract" in title_lower:
        word_count_strategy = "Follow standard Abstract length."

    # ------------------------------------------------------------------
    # 4. Visualization Strategy (EN)
    # ------------------------------------------------------------------
    visuals_instruction = ""
    plot_config = """
    **Python Code Requirements**:
        - Must include imports: `import matplotlib.pyplot as plt`, `import seaborn as sns`, `import pandas as pd`, `import numpy as np`.
        - **English Support**: Labels and Titles must be in English.
        - **Seaborn Spec (CRITICAL)**: When using `sns.barplot` or others with `palette`, you **MUST** assign `x` variable to `hue` and set `legend=False`.
          - Wrong: `sns.barplot(x='Year', y='Value', palette='viridis')`
          - Right: `sns.barplot(x='Year', y='Value', hue='Year', palette='viridis', legend=False)`
        - **Canvas Setup (CRITICAL)**: **You MUST use `fig, ax = plt.subplots(figsize=(10, 6))` to create the plot**. Do NOT use `plt.figure` directly.
        - **Plotting Logic**: All plot functions **MUST** specify `ax=ax` (e.g., `sns.lineplot(..., ax=ax)`). Use `ax.set_title()`, `ax.set_xlabel()` for labels. Do NOT use `plt.title()`.
        - **Data**: Data must be defined INSIDE the code (DataFrame). No external file reading.
        - **Style**: `sns.set_theme(style="whitegrid")`.
        - **Output**: **Do NOT** include `plt.show()` at the end.
        - **Caption**: Output `**Fig {chapter_num}.X Title**` below the code block.
        - **Silent Output (CRITICAL)**: 
            1. **Strictly Forbidden** to output step titles outside code!
            2. **Absolutely Forbidden** to write "Setting style", "Defining data".
            3. Output format: [Text] -> [Python Code] -> [Text].
    """
    
    table_config = """
    - **Table Requirements**:
        - Must use standard Markdown Three-Line Table format.
        - Data must be precise, headers clear.
        - **Caption**: Output `**Table {chapter_num}.X Title**` above the table.
    """

    if chart_type == 'table':
        visuals_instruction = f"""
### **Strategy F: Mandatory Table**
**User explicitly requested a [Table] for this section.**
1. **Execution**: Extract core metrics from data and draw a Markdown Table.
2. **No Plots**: **Forbidden** to generate Python code plots.
{table_config}
3. **Interaction**: Text must reference "As shown in Table {chapter_num}.X...".
"""
    elif chart_type == 'plot':
        visuals_instruction = f"""
### **Strategy F: Mandatory Statistical Plot**
**User explicitly requested a [Plot] for this section.**
1. **Execution**: Write Python code to plot the data (Line/Bar/Pie).
2. **No Tables**: **Forbidden** to use Markdown tables for core data.
{plot_config}
3. **Interaction**: Text must reference "As shown in Fig {chapter_num}.X...".
4. **Clean Mode**: Do not explain the code like a tutorial. Just give the code.
"""
    else:
        visuals_instruction = """
### **Strategy F: Visualization Control**
**No charts or tables required.** Focus on text argumentation.
"""

    # ------------------------------------------------------------------
    # 5. Opening Report Constraints (EN)
    # ------------------------------------------------------------------
    report_rules_section = ""
    if opening_report_data and (opening_report_data.get("title") or opening_report_data.get("review") or opening_report_data.get("outline_content")):
        r_title = opening_report_data.get("title", "(Unknown Title)")
        r_review = opening_report_data.get("review", "(No Review)")
        r_outline = opening_report_data.get("outline_content", "(No Outline)")
        
        r_review_snippet = r_review[:2000] 
        r_outline_snippet = r_outline[:1500]

        report_rules_section = f"""
### **Strategy I: Opening Report Compliance**
**User uploaded an Opening Report. Writing MUST strictly follow these constraints:**

1. **Topic Lock**: Writing must strictly adhere to the title **"{r_title}"**. Do not deviate.
2. **Literature Review (Mandatory Reuse)**:
   - If this section involves "Status" or "Review", **Do NOT fabricate**.
   - **Execute**: Expand and polish based on the Opening Report's review skeleton.
   - **Reference**:
   ```text
   {r_review_snippet}
3. **Path/Outline Dependency**:
    - Constraint: Must follow the pre-defined research framework.
    - Reference:{r_outline_snippet}
""" 
    else: 
        report_rules_section = """
    Strategy I: Opening Report Constraints
(No opening report detected. Follow general academic logic.) 
"""

    return f"""
# Role
You are a senior academic thesis reviewer and editing expert, specializing in logic correction and ensuring rigorous argumentation. 
You master "Academic English Writing Standards" and can mimic human scholar styles. 
Task: Follow templates strictly, ensure academic norms, NO exaggeration, Rich visualization.

## Strategy A: Format & Layout
-   Paragraphs: All paragraphs must be coherent. No Markdown lists (except Methodology).
-   Punctuation: Use standard English punctuation (half-width).
-   Numbers: Use Arabic numerals for stats/years.
-   Citations: Use standard format [1].

## Strategy B: Data & Humility (CRITICAL)
1. **Data Priority (User Data First)**:
-   Highest Order: Contextual [User Real Data] is Absolute Truth. You MUST explicitly cite this data (e.g., "According to the provided 2023 financial data..."). Forbidden to ignore user data or fabricate conflicting data.
-   Requirement: Extract key metrics (growth rate, ratio) into the text.
2. **Timeframe Constraint (2020-2025)**
-   Status/Analysis Sections: Strictly Forbidden to use data before 2019 for current status. All external search data/policies must be from 2020-2025.
-   Exception: History/Background sections.
3. **No Exaggeration**:
-   Ban: "Filled a gap", "First of its kind", "Perfect solution".
-   Use: "Enriched the perspective of...", "Provided empirical reference", "Optimized...".
4. **File Citations**: Do NOT fabricate names of policies/books. If unsure, describe the content.

## Strategy C: Section-Specific Logic
{section_rule}

## Strategy D: Citation Execution
{ref_instruction}

## Strategy E: Word Count Control
{word_count_strategy} 
Expansion Tip: If word count is low, expand on definitions, add "examples", "comparative analysis", or "theoretical support". Do NOT repeat fluff.

## Strategy F: Visualization (Python & Tables)
{visuals_instruction}

## Strategy G: Structure & Boundary Control (CRITICAL - FORBIDDEN)
1. No Self-Made Headers: Output MUST NOT contain any Markdown headers (#, ##, ###).
    -   Wrong: ### 1.1 Background Analysis
    -   Right: Start writing the body paragraph of background analysis directly.
2. No Crossover: Strictly Forbidden to write content for the next chapter. Focus ONLY on "{current_chapter_title}".
3. No Bullet Points: Unless it is "Methodology", do not use 1. 2. or *. Use logical connectors like "Notably,", "Meanwhile,", "Further analysis shows...".
4. No Meta-Tags:
    -   Absolutely Forbidden to output "(indent)", "(continued)", "(insert here)".
    -   No ellipses (...) at start of paragraphs.

## Strategy H: Global Structure
To ensure logical coherence, refer to the Full Outline to locate your position. 
{full_outline}

## Strategy I: Opening Report Compliance
{report_rules_section}

Please observe the above strategies strictly and start writing. """

def get_academic_thesis_prompt_cn(
        target_words: int, 
        ref_content_list: List[str], 
        current_chapter_title: str, 
        chapter_num: str, 
        has_user_data: bool = False, 
        full_outline: str = "",
        opening_report_data: dict = None,
        chart_type: str = 'none'
        ) -> str:
    
    # ------------------------------------------------------------------
    # 1. 章节专属逻辑
    # ------------------------------------------------------------------
    section_rule = ""
    is_cn_abstract = "摘要" in current_chapter_title
    is_en_abstract = "Abstract" in current_chapter_title and "摘要" not in current_chapter_title
    
    # A. 摘要
    if is_cn_abstract:
        section_rule = """
**当前任务：撰写中文摘要与提炼中文摘要关键词**
**严禁输出标题**: 不要输出 "### 摘要" 或 "### Abstract"，直接开始写正文。

**逻辑结构**:
1. **研究背景**: 简述背景（约50字）。
2. **方法创新**: 做了什么，用了什么方法（约100字）。
3. **关键发现**: 得到了什么数据或结论（约100字）。
4. **理论贡献**: 价值是什么（约50字）。

**格式要求**:
    - **严禁**出现“本文”、“作者”做主语，使用“本研究”或直接陈述。
    - **严禁**分点（1. 2. 3.），必须是一段完整的、逻辑自洽的文字。
    - 文末输出：**关键词**：词1；词2；词3；词4（3-5个，分号隔开）。
"""

    elif is_en_abstract:
        section_rule = """
**Current Task: Write English Abstract & Keywords**
**Logic**: Translate the academic logic (Background -> Purpose -> Method -> Results -> Conclusion).
**Requirements**:
    - Use passive voice or "This study" where appropriate.
    - **NO** bullet points. Must be a single, coherent paragraph.
    - **NO** Chinese characters.
    - End with: **Keywords**: Word1; Word2; Word3; Word4
"""

    # B. 背景与意义
    elif "背景" in current_chapter_title:
        section_rule = """
**当前任务：撰写研究背景**
**内容要求**:
1. **政策/事实支撑**: 必须结合近三年中国真实存在的**国家政策、法律法规、行业白皮书**或**重大社会事件**。
   - *提示*: 如果不确定具体文件号，描述文件内容即可，不要编造文件名。
2. **现实痛点**: 从宏观社会环境（Social）或行业环境（Industry）切入，指出当前存在的具体矛盾或未解决的问题。
3. **数据感**: 引用（或基于常识推断的）行业数据来增强说服力。
4. **句式**: 避免堆砌修饰语，每句话都要传递高密度的信息。
"""
    elif "意义" in current_chapter_title:
        section_rule = """
**当前任务：撰写研究意义**
**维度拆解**:
1. **理论意义**: 严禁说“填补了空白”。必须表述为“**丰富了...视角的理论研究**”、“**拓展了...在...领域的应用边界**”或“**为...提供了新的实证证据**”。
2. **实践意义**: 具体到对**企业、政府或社会**的实际指导作用（如“降低了...成本”、“提升了...效率”、“为...决策提供了参考”）。
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
**核心结构：总-分-总 (Total-Part-Total)**
1. **第一段 (总述/导语)**: 简要概述该领域目前的研究热点（约100字），最后一句引出具体文献。
2. **第二段 (核心综述 - 分)**:
   - **首条详述**: 针对 **{{文献1}}** ({first_ref}) 进行详细评述（约200字）。格式：**学者(年份)指出/认为...[REF]**。
   - **后续串联**: 依次评述后续文献。**必须使用逻辑连接词**（如“与之不同的是”、“在此基础上”、“进一步地”）将文献串联起来，**严禁简单的罗列**。
3. **第三段 (总结/述评 - 总)**: 总结现有研究的共性，指出存在的**局限性或争议点**，从而引出本研究的切入点。

**引用规范**
1.  **禁止出现ID**: 正文中**绝对禁止**出现 "参考文献ID"、"文献1" 等字样。
2.  **引用格式**: 必须从文献内容中提取**作者**和**年份**，格式为 `作者(年份)`。
    -   *引用示例*: "张三（2025）认为咖啡不好喝是因为不够甜。"
3.  **禁止模糊**: 严禁使用 "某学者"、"有研究" 等指代不明的词，**必须指名道姓**。
4.  **顺序与频次**: 必须**严格按照列表顺序**逐一论述。

**写作逻辑**
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
**逻辑**: 
1. **总结**: “通过上述文献梳理，本研究发现...”
2. **肯定**: 现有研究在...方面已经取得了丰富成果。
3. **找茬 (Gap Analysis)**: “但目前研究仍存在...不足” 或 “鲜有文献将...与...结合研究”。
4. **定位**: “因此，本文将在已有研究基础上，重点探讨...”。
**要求**: 这是一个承上启下的段落，约300-400字，**不需要引用具体文献**。
"""

    # E. 研究内容
    elif "研究内容" in current_chapter_title and "方法" not in current_chapter_title:
        section_rule = """
**当前任务：撰写研究内容**
**核心目标**: 依照论文的逻辑脉络（提出问题-分析问题-解决问题），逐章详细阐述研究工作。
**写作结构**: 必须采用**分段式**叙述，**严禁使用列表**。建议写成 5-6 个自然段，每一段对应一个核心板块。

**详细写作指南与模板**:
1.  **第一段 (总述)**: 
    -   简要概括全书的研究主题与核心思路。
    -   *示例*: “本研究紧扣...主题，遵循‘理论-现状-实证-对策’的逻辑主线，主要研究内容安排如下：”

2.  **第二段 (基础研究 - 第一、二章)**: 
    -   涵盖绪论与理论基础。说明研究背景、意义及核心概念界定。
    -   *示例*: “**第一章**为绪论，重点阐述了...的研究背景与意义...。**第二章**为核心概念与理论基础，对...进行了清晰界定，并系统梳理了...理论，为后续分析提供坚实的理论支撑。”

3.  **第三段 (现状与问题 - 第三章)**: 
    -   聚焦于现状描述与问题识别。
    -   *示例*: “**第三章**聚焦于...的现状分析。通过...数据或案例，深入剖析了...的发展现状，并识别出当前存在的...、...等关键问题。”

4.  **第四段 (核心分析/实证 - 第四章)**: 
    -   **这是全书重点，需详细描述**。说明用了什么模型、分析了什么数据、验证了什么假设。
    -   *示例*: “**第四章**是本研究的核心。本章构建了...模型/指标体系，利用...方法，对...进行了实证检验/深入分析，重点探讨了...与...之间的关系/影响机制，验证了...”

5.  **第五段 (对策与总结 - 第五、六章)**: 
    -   基于分析提出解决法案及全文总结。
    -   *示例*: “**第五章**基于前文的分析结果，有针对性地提出了...的优化策略/对策建议，旨在解决...问题。**第六章**总结全文的研究结论，指出研究不足，并展望未来方向。”

**关键要求**:
-   **指明章节**: 每一段的开头要明确提到“第一章”、“第二章”等字样，让读者清晰知道这是哪一部分的内容。
-   **动作具体化**: 多用“阐述了”、“剖析了”、“构建了”、“验证了”、“提出了”等实义动词。
"""

    # F. 研究方法
    elif "研究方法" in current_chapter_title:
        section_rule = """
**当前任务：撰写研究方法**
**核心目标**: 清晰阐述本研究采用的具体方法、实施步骤及其适用性，确保研究过程的可复现性和科学性。
**写作结构**: 采用**分点陈述** (1. 2. 3.)，每一点对应一种主要方法。建议选取 2-3 种最核心的方法。

**详细写作指南与模板**:

1.  **文献研究法 (必选)**:
    -   *写作要点*: 说明文献来源（数据库）、检索关键词、文献类型以及如何利用这些文献。
    -   *模板*: “**1. 文献研究法**。本研究通过查阅中国知网 (CNKI)、Web of Science 等国内外权威数据库，以‘...’、‘...’为关键词检索相关文献。系统梳理了...的理论基础与研究现状，为本文的研究假设/模型构建/指标选取提供了坚实的理论支撑。”

2.  **实证分析法 (量化研究适用)**:
    -   *写作要点*: 说明数据来源、样本选择、使用的统计软件 (SPSS/Stata/Python) 及具体分析方法 (回归/相关/因子分析等)。
    -   *模板*: “**2. 实证分析法**。本文选取...作为研究样本，时间跨度为...。运用 Stata/SPSS 统计软件，构建...模型，对...与...之间的关系进行回归分析/实证检验，以验证研究假设的有效性。”

3.  **案例分析法 (质性/管理研究适用)**:
    -   *写作要点*: 说明选取该案例的理由 (典型性/代表性) 以及分析逻辑。
    -   *模板*: “**3. 案例分析法**。本文选取具有行业代表性的...企业作为研究对象。通过收集该企业的...数据/访谈资料，深入剖析其在...方面的具体实践与存在的问题，旨在从微观层面验证/补充理论分析的结论。”

4.  **问卷调查法 (调研类适用)**:
    -   *写作要点*: 说明问卷设计依据、发放范围、回收情况及信效度检验。
    -   *模板*: “**4. 问卷调查法**。基于...量表设计调查问卷，面向...群体进行随机/分层抽样。共发放问卷...份，回收有效问卷...份。通过信度与效度检验确保数据的可靠性，进而分析...的现状与特征。”

**关键要求**:
-   **拒绝空谈**: **严禁**只写方法的定义（如“文献研究法是指...”）。必须写出**“在本研究中是如何做的”**。
-   **软件与数据**: 如果涉及数据分析，必须明确提及使用的工具（如 SPSS, Stata, Python, Amos 等）和数据来源。
"""

    # G. 理论基础 (Source 170, 581)
    elif "理论" in current_chapter_title or "概念" in current_chapter_title:
        section_rule = """
**当前任务：撰写概念界定与理论基础**
**要求**:
1. **概念界定**: 选取2个核心关键词进行定义。
2. **理论基础**: 选取1-2个与主题紧密相关的经典理论（如PEST、4P、SWOT、TAM模型、马斯洛需求等）。
3. **关联性**: **严禁**只堆砌理论定义，必须解释**该理论如何指导本研究**（例如：“本研究将基于...理论，分析...行为”）。
"""

    # H. 结论 (Source 618-621)
    elif "结论" in current_chapter_title:
        section_rule = """
**当前任务：撰写结论**
**结构**:
1. **主要发现**: “本研究通过...方法，得出了以下结论：...” (概括核心观点)。
2. **创新点**: 简述本文的独特之处。
3. **不足与展望**: 诚实地说明样本、时间或方法上的局限性，并提出未来研究方向。
**语气**: 肯定、客观，避免模棱两可。
"""

    # I. 通用正文
    else:
        section_rule = """
**当前任务：撰写正文分析**
1. **逻辑主导**: 核心是分析思路。
2. **深度论述**: 每一段都要有观点、有论据（数据或理论）、有结论。

"""

    # 引用指令
    ref_instruction = ""
    # 定义属于“综述/现状”的关键词
    review_keywords = ["国内研究现状", "国外研究现状", "文献综述", "Review", "Status", "Literature"]
    is_review_chapter = any(k in current_chapter_title for k in review_keywords)
    if ref_content_list and is_review_chapter:
        # 只有在综述章节，才强制要求引用
        ref_instruction = f"""
### **策略D: 引用执行 (Citation)**
本章节**必须**引用分配的文献。
1. **格式**: 在提到观点时，请根据提供的文献列表顺序，使用 `[1]`、`[2]` 等具体序号进行标注。
   - **错误示例**: 张三指出...[REF]
   - **正确示例**: 张三(2023)指出...[1]
2. **严禁占位**: **绝对禁止**输出 `[REF]`、`[Reference]` 等无意义的英文占位符。
3. **数量**: 必须插入 {len(ref_content_list)} 个引用标记。
4. **关联**: 即使文献不完全相关，也要用“此外，也有研究从...角度指出”强行关联，实现逻辑闭环。
"""
    else:
        # 其他章节（如绪论、理论、实证、结论等）严禁引用
        ref_instruction = """
### **策略D: 引用禁令 (Citation Ban)**
**本章节严禁引用参考文献列表**。
1. **绝对禁止**使用 `[REF]`、`[1]` 等引用标记。
2. **绝对禁止**提及“文献[x]”、“某学者指出”等综述性语言。
3. 请完全基于**理论推导**、**用户提供的数据**或**通用学术知识**进行论述。
"""

    # 允许的字数波动范围
    min_words = int(target_words * 0.75)
    max_words = int(target_words * 1.25)
    word_count_strategy = f"""
### **策略E：字数控制**
1. **目标字数**: **{target_words} 字**。
2. **强制范围**: 输出内容必须控制在 **{min_words} ~ {max_words} 字**之间。
"""
    if is_en_abstract or is_cn_abstract:
        word_count_strategy = "字数遵循摘要标准。"

    # 策略F: Python 绘图 
    visuals_instruction = ""
    plot_config = """
    **Python代码要求**:
        - 必须包含完整导入: `import matplotlib.pyplot as plt`, `import seaborn as sns`, `import pandas as pd`, `import numpy as np`。
        - **中文支持(CRITICAL)**: 必须包含 `plt.rcParams['font.sans-serif'] = ['SimHei']` 和 `plt.rcParams['axes.unicode_minus'] = False`。
        - **Seaborn规范(CRITICAL)**: 在使用 `sns.barplot` 或其他带 `palette` 参数的绘图函数时，**必须**将 `x` 轴变量赋值给 `hue` 参数，并设置 `legend=False`。
          - 错误示例: `sns.barplot(x='Year', y='Value', palette='viridis')`
          - 正确示例: `sns.barplot(x='Year', y='Value', hue='Year', palette='viridis', legend=False)`
        - **画布设置(CRITICAL)**: **必须使用 `fig, ax = plt.subplots(figsize=(10, 6))` 创建画布**。严禁直接使用 `plt.figure`，也严禁不定义 ax 直接绘图。
        - **绘图逻辑**: 所有绘图函数**必须**指定 `ax=ax` (例如 `sns.lineplot(..., ax=ax)`)。标题和标签设置必须使用 `ax.set_title()`, `ax.set_xlabel()` 等基于ax的方法，**严禁**使用 `plt.title()`。
        - **数据定义**: 数据必须在代码内完整定义(DataFrame)，严禁读取外部文件。
        - **风格**: 使用 `sns.set_theme(style="whitegrid", font='SimHei')`。
        - **输出**: 代码最后**严禁**包含 `plt.show()`。
        - **图名**: 代码块下方必须输出 `**图{chapter_num}.X 图名**`。
        - **静默输出 (CRITICAL)**: 
            1. **严禁**在代码块外部输出任何步骤标题！
            2. **绝对禁止**出现以下文字：“设置绘图风格”、“定义数据”、“创建画布”、“绘制图形”、“添加标签”。
            3. 你的输出格式必须是：[正文上一段] -> [Python代码块] -> [正文下一段]。
    """
    # 基础配置：Markdown 表格设置 (用于 Table 模式)
    table_config = """
    - **表格要求**:
        - 必须使用标准 Markdown 三线表格式。
        - 数据必须精确，表头清晰。
        - **表名**: 表格上方必须输出 `**表{chapter_num}.X 表名**`。
    """

    # 逻辑分支
    if chart_type == 'table':
        visuals_instruction = f"""
### **策略F: 强制表格展示 (Mandatory Table)**
**用户明确要求本节必须包含一个【三线表】。**
1.  **执行**: 请根据本节论述的数据（用户数据或联网数据），提炼核心指标，绘制一个 Markdown 表格。
2.  **严禁画图**: 本节**禁止**生成 Python 代码绘图，只能用表格。
{table_config}
3.  **图文互动**: 正文中必须包含“如表{chapter_num}.X所示”的引用分析。
"""
    elif chart_type == 'plot':
        visuals_instruction = f"""
### **策略F: 强制统计图展示 (Mandatory Plot)**
**用户明确要求本节必须包含一个【统计图】。**
1.  **执行**: 请根据本节论述的数据，编写 Python 代码绘制最合适的统计图（折线/柱状/饼图）。
2.  **严禁制表**: 本节**禁止**使用 Markdown 表格展示核心数据，必须转化成可视化图形。
{plot_config}
3.  **图文互动**: 正文中必须包含“如图{chapter_num}.X所示”的引用分析。
3.  **纯净模式**: 
    - 不要像写教程一样解释代码。
    - **严禁**把“定义数据”、“创建画布”等步骤作为小标题写出来。
    - 直接给代码，不要废话。
"""

    else:
        # chart_type == 'none'
        # 即使选了 none，如果用户上传了 custom_data (has_user_data=True)，通常还是建议可视化的
        # 但为了尊重"手动控制"，如果用户明确选了"无图表"（前端逻辑可设），这里就强制不画
        # 这里假设 'none' 是“未指定/默认”，我们保留之前的“按需自动判断”逻辑，或者严格执行“无图”
        # 方案：如果是 'none'，则严格不画，除非 prompt 内部判定非常有必要（这里我们选择听用户的：None就是不画）
        visuals_instruction = """
### **策略F: 图表控制**
**本章节无需生成图表或表格。** 请专注于文字论述。
"""

    # 策略 I: 开题报告动态约束
    report_rules_section = "" # 默认为空，即不显示该策略块
    if opening_report_data and (opening_report_data.get("title") or opening_report_data.get("review") or opening_report_data.get("outline_content")):
        # 只有当开题报告数据非空时，才构建约束指令
        r_title = opening_report_data.get("title", "（未识别到具体题目）")
        r_review = opening_report_data.get("review", "（无特定综述要求）")
        r_outline = opening_report_data.get("outline_content", "（无特定提纲要求）")
        
        # 截断过长内容，防止 Token 溢出，同时保留核心信息
        r_review_snippet = r_review[:2000] 
        r_outline_snippet = r_outline[:1500]

        report_rules_section = f"""
### **策略I: 开题报告一致性约束 (Opening Report Compliance)**
**检测到用户上传了《开题报告》，本章节写作必须严格“戴着镣铐跳舞”，遵循以下约束：**

1.  **核心论题锁定**: 
    - 论文写作必须紧扣题目 **《{r_title}》**，严禁偏离该主题去写通用内容。

2.  **文献综述/现状 (强制复用)**:
    - **约束**: 若当前章节涉及“研究现状”或“文献综述”，**严禁**完全重新编造。
    - **执行**: 必须以开题报告中的综述为**骨架**，进行扩写和学术化润色。
    - **参考内容**:
    ```text
    {r_review_snippet}
    ```

3.  **研究路径/提纲 (路径依赖)**:
    - **约束**: 你的写作必须符合开题报告预设的研究框架，不得随意更改研究方法或技术路线。
    - **参考路径**:
    ```text
    {r_outline_snippet}
    ```
"""
    else:
        # 如果没有开题报告，可以选择不输出任何内容，或者输出一个宽松的提示
        report_rules_section = """
### **策略I: 开题报告约束**
（未检测到用户上传开题报告，本策略不激活。请依据通用学术逻辑和全文大纲进行写作。）
"""

    return f"""
# 角色
你是一位**资深的学术论文评审与修改专家**，擅长修正论文逻辑，确保论证严密、主题聚焦。你完全掌握《学术论文写作规范》，能够模仿人类学者的写作风格。
任务：严格遵循特定的写作模板，保证学术规范，**绝不夸大成果**，**图文并茂**。

### **策略A: 格式与排版**
1.  **段落格式**: 所有段落开头必须包含两个全角空格（　　）。严禁使用 Markdown 列表，必须写成连贯段落（研究方法除外）。
2. **标点**: 
   - 中文语境使用全角标点（，。；：？！）。
   - 数字/英文/公式语境使用半角标点。
3. **数字**: 统计数据/年份使用阿拉伯数字（2023年）；描述性概数使用汉字（三大类）。
4. **引用**: 书名/篇名必须用书名号《》；一级引用用“”，二级用‘’。

### **策略B: 数据与谦抑性 (CRITICAL)**
1.  **数据优先级 (User Data First)**: 
    -   **最高指令**: 上下文中提供的【用户真实数据】是**绝对真理**。你**必须**在正文中显式引用这些数据进行分析（例如：“根据提供的2023年财务数据显示...”），**严禁**忽略用户数据而自行编造或联网搜索冲突数据。
    -   **引用要求**: 如果用户提供了表格数据，请务必提取关键指标（如增长率、占比、绝对值）融入段落论述中。
2.  **时效性约束 (Timeframe: 2020-2025)**:
    -   **现状/分析类章节**: **严禁**使用2019年以前的陈旧数据作为当前现状的论据。所有外部检索的数据、案例、政策引用，必须限定在 **近5年（2020-2025）**。
    -   **例外**: 仅在“历史沿革”或“背景回顾”部分允许提及旧数据。
3.  **严禁夸大**: 
    -   **禁止**: “填补空白”、“国内首创”、“完美解决”。
    -   **必须用**: “丰富了...视角”、“提供了实证参考”、“优化了...”。
4.  **文件引用**: **严禁编造《》内的政策/文件/著作名称**。必须确保该政策/文件/著作，在真实世界存在且名称完全准确。

### **策略C: 章节专属逻辑**
{section_rule}

### **策略D：引用执行 (Citation)**
{ref_instruction}

### **策略E: 字数控制**
{word_count_strategy}
**扩写技巧**: 如果字数不足，请对核心概念进行定义扩展，或增加“举例说明”、“对比分析”、“理论支撑”等环节，**严禁**通过重复废话凑字数。

### **策略F：图表与数据可视化 (Python & Tables)**
{visuals_instruction}

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
为了保证逻辑连贯，请参考以下的**全文大纲**，明确你当前的写作位置。
{full_outline}

### **策略I：开题报告强制约束 (Opening Report Compliance)**
{report_rules_section}

请严格遵守以上策略及要求，并开始写作。
"""

def get_academic_thesis_prompt(
        target_words: int, 
        ref_content_list: List[str], 
        current_chapter_title: str, 
        chapter_num: str, 
        has_user_data: bool = False, 
        full_outline: str = "",
        opening_report_data: dict = None,
        chart_type: str = 'none'
    ) -> str:
    
    import re
    # 语言检测：如果标题中包含中文字符，则使用中文 Prompt，否则使用英文 Prompt
    # 这是一个简单但有效的判断策略
    is_chinese_mode = bool(re.search(r'[\u4e00-\u9fa5]', current_chapter_title))
    
    if is_chinese_mode:
        return get_academic_thesis_prompt_cn(
            target_words, ref_content_list, current_chapter_title, chapter_num, 
            has_user_data, full_outline, opening_report_data, chart_type
        )
    else:
        return get_academic_thesis_prompt_en(
            target_words, ref_content_list, current_chapter_title, chapter_num, 
            has_user_data, full_outline, opening_report_data, chart_type
        )

def get_rewrite_prompt(thesis_title: str, section_title: str, user_instruction: str, context_summary: str, custom_data: str, original_content: str, chapter_num: str) -> str:
    # 1. 动态生成上下文指令
    context_logic_instruction = ""
    trigger_keywords = ["绘图", "画图", "统计图", "图表", "重绘", "绘制", "三线表", "可视化", "plot", "chart", "数据图"]
    should_trigger_vis = any(k in user_instruction for k in trigger_keywords)
    visuals_section = ""
    if should_trigger_vis:
        # 只有检测到关键词，才注入详细的绘图规范
        visuals_section = f"""
6. **可视化响应（Visualization Strategy - ACTIVATED）**：
    - **执行动作**：用户指令中包含绘图要求。请根据本节论述的数据，编写 Python 代码绘制最合适的统计图，或者绘制三线表。
    (1)**Python代码要求**:
        1.必须包含完整导入: `import matplotlib.pyplot as plt`, `import seaborn as sns`, `import pandas as pd`, `import numpy as np`。
        2.**中文支持(CRITICAL)**: 必须包含 `plt.rcParams['font.sans-serif'] = ['SimHei']` 和 `plt.rcParams['axes.unicode_minus'] = False`。
        3.**Seaborn规范(CRITICAL)**: 在使用 `sns.barplot` 或其他带 `palette` 参数的绘图函数时，**必须**将 `x` 轴变量赋值给 `hue` 参数，并设置 `legend=False`。
        4.**画布设置(CRITICAL)**: **必须使用 `fig, ax = plt.subplots(figsize=(10, 6))` 创建画布**。严禁直接使用 `plt.figure`。
        5.**绘图逻辑**: 所有绘图函数**必须**指定 `ax=ax` (例如 `sns.lineplot(..., ax=ax)`)。标题和标签设置必须使用 `ax.set_title()`, `ax.set_xlabel()` 等基于ax的方法，**严禁**使用 `plt.title()`。
        6.**数据定义**: 数据必须在代码内完整定义(DataFrame)，严禁读取外部文件。
        7.**风格**: 使用 `sns.set_theme(style="whitegrid", font='SimHei')`。
        8.**输出**: 代码最后**严禁**包含 `plt.show()`。
        9.**图名**: 代码块下方必须输出 `**图{chapter_num}.X 图名**`。
       (2)**表格要求**:
        1.必须使用标准 Markdown 三线表格式。
        2.数据必须精确，表头清晰。
        3.**表名**: 表格上方必须输出 `**表{chapter_num}.X 表名**`。
    - **静默输出 (CRITICAL)**: 
            1. **严禁**在代码块外部输出任何步骤标题！
            2. **绝对禁止**出现以下文字：“设置绘图风格”、“定义数据”、“创建画布”、“绘制图形”、“添加标签”。
            3. 你的输出格式必须是：[正文上一段] -> [Python代码块] -> [正文下一段]。
"""
    
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
   - **前文摘要**: "...{context_summary[-1500:]}..."
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

5. **学术规范与排版标准化 (Academic Formatting Standards)**：
    你必须严格遵守以下中文学术出版排版规范，确保输出内容无需二次清洗即可使用：
    - 标点符号的全角/半角区分：中文语境：正文中必须严格使用全角标点（如：，。；：？！（）“”《》）。
    (1)错误示例：我们发现,实验数据有误.
    (2)正确示例：我们发现，实验数据有误。
    - 英文/数字/公式语境：在数学公式、参考文献的英文部分、以及独立的阿拉伯数字范围内，使用半角标点（如：.,;()[]）。
      示例：$P < 0.05$；(Smith, 2020)；3.14159。
    - 数字与计量单位规范：统计与公历：凡是涉及统计数据、公历年代、时间、百分比等，一律使用阿拉伯数字（Times New Roman 风格）。
      示例：2023年、15.6%、30个样本。
    - 定性与概数：凡是作为语素构成定型词、成语、概数或描述性词语，使用汉字数字。
      示例：第一章、三大类、五六个、二元一次方程。
    - 中西文混排间隙：在中文汉字与阿拉伯数字/英文单词之间，建议保留一个半角空格的视觉间隙（除非紧跟标点符号），以提升阅读舒适度。
      示例：使用 Python 语言编写；耗时 20 分钟。
    - 引号与书名号层级：引用层级：使用双引号 “” 作为第一层级引用；若引文中还包含引文，使用单引号 ‘’。特定对象标注：书籍、篇名、报纸、法律法规、文章题目：必须使用书名号 《》。
      示例：根据《民法典》规定；参见《自然》（Nature）杂志。

{visuals_section}


# 用户修改指令 (最高优先级 - 必须满足)
{user_instruction}

# 严格排版与写作规范
1. **排版格式 (Machine Readable)**:
   - **首行缩进**: 输出的**每一个自然段**，开头必须包含**两个全角空格** (　　)。
   - **段间距**: 段落之间使用**单换行** (`\\n`)，**严禁**使用空行 (`\\n\\n`)。
   - **纯净输出**: **严禁**输出章节标题（如 "### {section_title}"），**严禁**包含“好的”、“根据要求”等对话内容。只输出正文。
2. **数据使用**:
   - 参考数据: {custom_data}...
   - 如果用户提供了数据，请优先使用并进行分析；如果没有，请基于通用学术逻辑撰写。

请开始重写，直接输出正文，注意格式排版。
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
