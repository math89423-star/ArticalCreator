import re
import json
import time
from typing import List
from openai import OpenAI
from typing import Dict, Generator
from .reference import ReferenceManager
from .word import TextCleaner

TASK_STATES = {}

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
        section_rule = """
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
            # Python逻辑修复：必须传入真实内容，而非ID占位符
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
    -   请编写一段**标准、无错、可直接运行的 Python 代码**。
    -   **代码块格式**: 使用 ` ```python ` 包裹。
    -   **关键要求 (CRITICAL)**: 
        -   **库导入**: 必须在代码开头显式导入：`import matplotlib.pyplot as plt`, `import seaborn as sns`, `import pandas as pd`, `import numpy as np`。
        -   **数据自包含**: 数据必须在代码内部完整定义（使用 DataFrame 或字典），**严禁**读取外部文件。
        -   **格式规范**: 严禁使用全角空格（\\u3000）或不间断空格（NBSP），必须使用标准空格缩进。
        -   **字体设置**: 必须包含 `plt.rcParams['font.sans-serif'] = ['SimHei', 'Arial Unicode MS', 'sans-serif']` 解决中文乱码。
        -   **绘图逻辑**: 代码需简单健壮，不要使用复杂或过时的 API。
        -   **输出**: 最后**不需要** `plt.show()`。
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
3.  **真实性**: 引用真实数据，严禁捏造。
4.  **文件引用**: **严禁编造《》内的政策/文件/著作名称**。必须确保该文件在真实世界存在且名称完全准确。如果不确定真实全称，**严禁使用书名号**，仅描述其内容即可。


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
3.  **禁止分点**: 除非是“研究方法”章节，否则严禁使用 `1.` `2.` 或 `*` 进行罗列，请用“首先、其次、此外”等连接词写成连贯段落。

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

            # --- [新增] 智能字数检查与扩写逻辑 ---
            # 统计有效字符数 (去除空白符)
            current_len = len(re.sub(r'\s', '', raw_content))
            # 如果字数少于目标的 60% (根据实际体验调整阈值)，强制扩写
            if current_len < target * 0.5:
                yield f"data: {json.dumps({'type': 'log', 'msg': f'   - 检测到字数不足 ({current_len}/{target})，进行深度扩写(禁止新增标题)...'})}\n\n"
                
                expand_prompt = (
                    f"当前输出字数 ({current_len}字) 未达到要求 ({target}字)。\n"
                    f"请对内容进行**深度扩写**，必须严格遵守以下红线：\n"
                    f"1. **零废话**：严禁输出“好的”、“如下所示”、“经过扩写”等任何对话式语句。**直接输出论文正文**。\n"
                    f"2. **引用保护**：所有参考文献引用（作者、年份、REF标记）必须**原样保留**，不可修改。\n"
                    f"3. **禁止标题**：严禁新增任何 Markdown 标题 (#/##)。\n"
                    f"4. **禁止统计**：文末严禁输出“(全文x字)”之类的统计语。\n"
                    f"请直接输出扩写后的内容。"
                )
                
                # 将初稿作为上下文，要求扩写
                expand_messages = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": raw_content},
                    {"role": "user", "content": expand_prompt}
                ]
                try:
                    # 使用临时调用进行扩写
                    resp = self.client.chat.completions.create(
                        model=self.model,
                        messages=expand_messages,
                        temperature=0.7
                    )
                    raw_content = resp.choices[0].message.content.strip()
                except Exception as e:
                    print(f"扩写失败: {e}")

            # 2. [新增] 字数过多 -> 精简
            elif current_len > target * 1.5:
                yield f"data: {json.dumps({'type': 'log', 'msg': f'   - 检测到字数过多 ({current_len}/{target})，正在进行精简...'})}\n\n"
                
                condense_prompt = (
                    f"当前输出字数 ({current_len}字) 远超要求 ({target}字)。\n"
                    f"请对内容进行**精简**，必须严格遵守以下红线：\n"
                    f"1. **零废话**：严禁输出“好的”、“已为您精简”等任何对话式语句。**直接输出论文正文**。\n"
                    f"2. **引用绝对保留**：原文中的所有参考文献引用（如 '作者(年份)...[REF]'）**必须原样保留**，严禁删除或修改。\n"
                    f"3. **禁止统计**：文末严禁输出“(全文x字)”之类的统计语。\n"
                    f"4. **严控篇幅**：目标字数 {target} 字左右。\n"
                    f"请直接输出精简后的内容。"
                )
                
                condense_messages = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": raw_content},
                    {"role": "user", "content": condense_prompt}
                ]
                
                try:
                    resp = self.client.chat.completions.create(
                        model=self.model,
                        messages=condense_messages,
                        temperature=0.7
                    )
                    raw_content = resp.choices[0].message.content.strip()
                except Exception as e:
                    print(f"精简失败: {e}")


            # 方案：比对第一行和sec_title，如果高度相似则移除第一行
            temp_lines = raw_content.strip().split('\n')
            if temp_lines:
                # 去除 # * 和空格进行核心词比对
                first_line_core = re.sub(r'[#*\s]', '', temp_lines[0])
                title_core = re.sub(r'[#*\s]', '', sec_title)
                # 如果第一行包含标题核心内容，且长度没有比标题长太多（防止误删正文第一句），则判定为重复标题
                if title_core in first_line_core and len(first_line_core) < len(title_core) + 8:
                    raw_content = '\n'.join(temp_lines[1:])
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