
import re
import json
import time
import base64
import concurrent.futures
from openai import OpenAI
from typing import Dict, List, Generator, Optional
from .reference import ReferenceManager
from .word import TextCleaner
from .prompts import get_rewrite_prompt, get_word_distribution_prompt, get_academic_thesis_prompt
from .word import MarkdownToDocx
try:
    from docx import Document
except ImportError:
    Document = None
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None


class PaperAutoWriter:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        # 主线程客户端
        self.main_client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
    
    def _call_llm_with_client(self, client, system_prompt: str, user_prompt: str, images: list = None) -> str:
        """
        使用指定的 client 实例调用 LLM
        支持可选的 images 参数 (List[dict])，用于视觉模型输入
        """
        # 1. 构建消息体
        messages = [{"role": "system", "content": system_prompt}]

        if images and len(images) > 0:
            # === 多模态消息构建 (Multimodal) ===
            user_content = [{"type": "text", "text": user_prompt}]
            
            for img_file in images:
                try:
                    # 获取文件名后缀以确定 MIME type
                    filename = img_file.get('name', 'image.jpg').lower()
                    mime_type = "image/jpeg" # 默认
                    if filename.endswith('.png'): mime_type = "image/png"
                    elif filename.endswith('.webp'): mime_type = "image/webp"
                    elif filename.endswith('.gif'): mime_type = "image/gif"
                    elif filename.endswith('.bmp'): mime_type = "image/bmp"

                    # 读取流并转为 base64
                    stream = img_file.get('content')
                    if stream:
                        stream.seek(0) # 重置指针
                        b64_str = base64.b64encode(stream.read()).decode('utf-8')
                        
                        user_content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{b64_str}"
                            }
                        })
                except Exception as e:
                    print(f"⚠️ 处理图片出错: {e}")
            
            messages.append({"role": "user", "content": user_content})
        else:
            # === 纯文本消息构建 ===
            messages.append({"role": "user", "content": user_prompt})

        # 2. 发送请求
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages, # 使用构建好的 messages
                    temperature=0.7, 
                    stream=False
                )
                return response.choices[0].message.content.strip()
            except Exception as e:
                print(f"⚠️ [LLM Error] Attempt {attempt+1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    # 如果是最后一次尝试失败，向上抛出异常或返回空字符串
                    # 这里选择抛出，以便上层捕获错误信息
                    raise e

    def _call_llm(self, system_prompt: str, user_prompt: str, images: list = None) -> str:
        """调用方法 (增加 images 透传)"""
        return self._call_llm_with_client(self.main_client, system_prompt, user_prompt, images=images)

    def _research_phase_with_client(self, client, topic: str) -> str:
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    # [修改] 强调时间范围 2020-2025
                    {"role": "system", "content": "你是一名严谨的数据分析师。请重点检索**近5年（2020-2025）**的真实数据、最新政策和行业报告。忽略2019年以前的过时信息。"},
                    {"role": "user", "content": f"检索关于'{topic}'的真实事实（必须是2020年以后的数据）："}
                ],
                temperature=0.3, stream=False
            )
            return response.choices[0].message.content.strip()
        except: 
            return ""

    def _research_phase(self, topic: str) -> str:
        return self._research_phase_with_client(self.main_client, topic)

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
        # 计算纯文本长度（排除代码块）
        content_no_code = re.sub(r'```[\s\S]*?```', '', raw_content)
        current_len = len(re.sub(r'\s', '', content_no_code))
        # 如果目标字数很小，或者当前字数已经达标（例如达到目标的 60%），就不处理
        if target < 300 or current_len >= target * 0.6: 
            return raw_content
        # 构建扩写指令
        expand_prompt = user_prompt + f"\n\n【系统检测】当前字数仅 {current_len} 字，远低于目标 {target} 字。请在保持原有观点的基础上，大幅扩充细节、增加论据、展开理论分析，确保字数达标。"
        # 再次调用 LLM
        refined_content = self._call_llm(sys_prompt, expand_prompt)
        return refined_content

    def _fix_markdown_table_format(self, text):
        """
        强力修复表格格式
        1. 识别表格行，强制去除缩进 (防止被当做代码块)
        2. 确保表格与上方文本之间有空行 (Markdown 标准)
        """
        lines = text.split('\n')
        new_lines = []
        in_table = False
        
        for line in lines:
            # 兼容全角空格的去除
            stripped = line.strip().replace('\u3000', '')
            # 判定是否为表格行 (以 | 开头并结尾)
            # 宽松匹配：只要去空后以 | 开头且包含第二个 | 即可
            is_table_row = stripped.startswith('|') and stripped.count('|') >= 2
            if is_table_row:
                if not in_table:
                    # 检查上一行是否为空，如果不是，插入空行
                    if new_lines and new_lines[-1].strip() != '':
                        new_lines.append('') 
                    in_table = True
                # 写入去缩进后的行
                new_lines.append(stripped)
            else:
                if in_table:
                    # [退出表格]
                    # 插入空行
                    if stripped != '':
                        new_lines.append('')
                    in_table = False
                # 非表格行保持原样 (保留原有的缩进)
                new_lines.append(line)
        return '\n'.join(new_lines)

    def _prepare_data_context(self, chapter: Dict, sec_title: str, custom_data: str, local_client, title: str) -> tuple:
        """辅助方法：准备数据上下文 (含数据路由与联网搜索)"""
        facts_context = ""
        logs = []
        use_data_flag = chapter.get('use_data', False)
        has_user_data = False

        if "摘要" not in sec_title and use_data_flag:
            if custom_data and len(custom_data.strip()) > 5:
                cleaned_data = TextCleaner.convert_cn_numbers(custom_data)
                facts_context += f"""
\n================ 【本研究核心调研数据库 (Research Database)】 ================
{cleaned_data}
============================================================================

【⚠️ 数据使用最高指令 (Data Usage & Integration Rules)】：
1. **智能路由 (Smart Routing)**: 
   - 上方数据库包含多个 `<datasource>` (来源文件)。
   - 请根据当前章节标题 **“{sec_title}”**，智能筛选出与本章主题**最相关**的一个或几个文件进行分析。
   - **严禁串味**: 如果本章讲“财务”，请忽略“人员名单”类的数据。

2. **隐形融入 (Seamless Integration - CRITICAL)**:
   - **角色设定**: 你是论文的作者，这些数据是你**亲自调研、收集和整理**的一手资料。
   - **绝对禁语**: **严禁**在正文中出现“用户提供”、“上传的文件”、“根据给定的数据”、“附件中”等打破学术语境的词汇。
   - **正确写法**: 将数据转化为自然的学术论述。
     - ❌ 错误: “根据用户提供的《2023财报》显示...”
     - ✅ 正确: “根据2023年度财务报表数据显示...” / “数据显示，...” / “从资产负债情况来看...”
   - **图表配合**: 如果文中列举了大量数据，请用文字对数据背后的**趋势、占比、异常值**进行分析，而不仅仅是报账。

3. **数据实证**: 
   - 本章节 **必须** 引用上述数据库中的具体数值作为论据。
   - 没有数据的论述是空洞的，必须用数据说话（例如：“增长了15%”、“占比达到40%”）。
"""
                has_user_data = True
            
            # 联网搜索逻辑
            # facts = self._research_phase_with_client(local_client, f"{title} - {sec_title} 数据")
            # if facts:
            #    facts_context += f"\n【联网补充数据】:\n{facts}\n"
        
        return facts_context, has_user_data, logs

    def _prepare_ref_context(self, sec_title: str, ref_domestic: str, ref_foreign: str) -> tuple:
        """辅助方法：准备参考文献上下文"""
        logs = []
        target_ref_list = []
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
            raw_ref_text = f"{ref_domestic}\n{ref_foreign}"

        if raw_ref_text:
            target_ref_list = [line.strip() for line in raw_ref_text.split('\n') if line.strip()]
            
        return target_ref_list, logs

    def _generate_raw_content(self, client, title, sec_title, context_summary, target, 
                              facts_context, has_user_data, target_ref_list, 
                              full_outline_str, chart_type, extra_instructions) -> tuple:
        """辅助方法：构建 Prompt 并调用 LLM 生成原始内容"""
        logs = []
        chapter_num = self._extract_chapter_num(sec_title)
        # 自动检测语言模式 (用于决定 User Prompt 的语言)
        import re
        is_chinese_mode = bool(re.search(r'[\u4e00-\u9fa5]', sec_title))
        # 构建 System Prompt (内部会自动分发 CN/EN)
        sys_prompt = get_academic_thesis_prompt(
            target, 
            target_ref_list, 
            sec_title, 
            chapter_num, 
            has_user_data, 
            full_outline=full_outline_str,
            chart_type=chart_type
        )
        # 构建 User Prompt 
        user_prompt = ""
        if is_chinese_mode:
            # 中文指令
            user_prompt = f"题目：{title}\n章节：{sec_title}\n前文摘要：{context_summary}\n【重要约束】目标字数：{target}字\n{facts_context}"
            if extra_instructions and len(extra_instructions.strip()) > 0:
                user_prompt += f"\n\n【用户额外具体需求 (最高优先级)】\n{extra_instructions}\n"
        else:
            # 英文指令 (Strict Translation)
            user_prompt = f"Thesis Title: {title}\nChapter: {sec_title}\nContext Summary: {context_summary}\n[Constraint] Target Word Count: {target}\n{facts_context}"
            if extra_instructions and len(extra_instructions.strip()) > 0:
                user_prompt += f"\n\n[User Extra Instructions (High Priority)]\n{extra_instructions}\n"
        # 调用 LLM
        content = self._call_llm_with_client(client, sys_prompt, user_prompt)
        # 字数扩写检查 (双语适配)
        content_no_code = re.sub(r'```[\s\S]*?```', '', content)
        current_len = len(re.sub(r'\s', '', content_no_code))
        # 英文单词通常比汉字多，所以英文模式下字数阈值可以适当调整，或者按字符数估算
        # 这里简化处理，逻辑保持一致
        if "abstract" not in sec_title.lower() and "摘要" not in sec_title and target > 300 and current_len < target * 0.5:
            try:
                logs.append(f"   - ⚠️ Word count low ({current_len}/{target}), expanding...")
                expand_instruction = "\n\n请大幅扩写，增加细节，确保字数达标。" if is_chinese_mode else "\n\nPlease expand significantly, adding details to meet the word count requirement."
                content = self._call_llm_with_client(client, sys_prompt, user_prompt + expand_instruction)
            except Exception as e:
                print(f"Expansion failed: {e}")
                
        return content, logs

    def _process_code_blocks(self, content: str) -> str:
        """辅助方法：处理 Python 代码块、自动闭合与绘图执行"""
        
        # 1. 自动闭合修复
        if content.count('```') % 2 != 0:
            content += "\n```"

        # 2. 定义宽容的正则
        code_block_pattern = re.compile(r'(```\s*(?:python|py)?\s*[\s\S]*?```)', re.IGNORECASE)

        def replacer(match):
            full_block = match.group(1)
            # 提取纯代码
            lines = full_block.strip().split('\n')
            code_lines = [line for line in lines if '```' not in line]
            
            if not code_lines: return match.group(0)
            
            code = '\n'.join(code_lines).strip()
            if not code: return match.group(0)

            try:
                # 执行绘图
                img_buf = MarkdownToDocx.exec_python_plot(code)
                if img_buf:
                    b64_data = base64.b64encode(img_buf.getvalue()).decode('utf-8')
                    return f"\n![统计图](data:image/png;base64,{b64_data})\n"
                else:
                    return match.group(0)
            except Exception as e:
                print(f"Plot Execution Error: {e}")
                return match.group(0)

        # 执行替换
        return code_block_pattern.sub(replacer, content)

    def _process_single_chapter(self, task_bundle):
        """线程工作函数 (重构版)"""
        i = -1
        sec_title = "未知章节"
        logs = []
        
        try:
            # 1. 参数解包与校验
            if len(task_bundle) < 13: 
                return { "index": -1, "type": "error", "msg": f"参数不足: {len(task_bundle)}", "logs": [] }

            (api_key, base_url, model, task_id, title, chapter, 
             ref_domestic, ref_foreign, 
             custom_data, context_summary, index_val, 
             full_outline_str, extra_instructions) = task_bundle
            
            i = index_val
            sec_title = chapter.get('title', '无标题')
            target = int(chapter.get('words', 500))
            is_parent = chapter.get('is_parent', False)
            chart_type = chapter.get('chart_type', 'none')

            # 2. 标题与层级处理
            header_prefix = self._determine_header_prefix(chapter, sec_title)
            if is_parent or target <= 0:
                return {
                    "index": i, "type": "header_only", 
                    "content": f"{header_prefix} {sec_title}\n\n",
                    "logs": [f"生成标题: {sec_title}"]
                }

            # 3. 初始化 Client
            local_client = OpenAI(api_key=api_key, base_url=base_url, timeout=120.0)
            logs.append(f"🚀 [并发启动] 正在撰写: {sec_title}")

            # 4. 准备上下文 (数据 + 文献)
            facts_context, has_user_data, data_logs = self._prepare_data_context(
                chapter, sec_title, custom_data, local_client, title
            )
            logs.extend(data_logs)

            target_ref_list, ref_logs = self._prepare_ref_context(
                sec_title, ref_domestic, ref_foreign
            )
            logs.extend(ref_logs)

            # 5. 生成核心内容 (含扩写重试)
            content, gen_logs = self._generate_raw_content(
                local_client, title, sec_title, context_summary, target,
                facts_context, has_user_data, target_ref_list,
                full_outline_str, chart_type, extra_instructions
            )
            logs.extend(gen_logs)

            # 6. 后处理 (代码执行、格式清洗)
            content = self._process_code_blocks(content)
            content = self._clean_and_format(content, sec_title, None)
            final_content = self._fix_markdown_table_format(content)
            
            # 7. 组装结果
            section_md = f"{header_prefix} {sec_title}\n\n{final_content}\n\n"

            return {
                "index": i, "type": "content", 
                "content": section_md, "raw_text": final_content, "logs": logs
            }

        except Exception as e:
            err_msg = f"❌ {sec_title} 异常: {str(e)}"
            print(f"[Thread {i}] ERROR: {err_msg}")
            # 打印详细堆栈以便调试
            import traceback
            traceback.print_exc()
            return { "index": i, "type": "error", "msg": str(e), "logs": [err_msg] }
        
    def write_section_content(self, 
                              section_title: str, 
                              word_count: int, 
                              references: List[str], 
                              full_outline_str: str,
                              chapter_num: str,
                              has_data: bool = False,
                              opening_report: Optional[Dict] = None) -> Generator[str, None, None]:
        """
        流式生成章节内容
        :param opening_report: 解析后的开题报告字典 (title, review, outline_content)
        """
        
        # 1. 策略 A: 直接内容复用 (Direct Hit)
        # 如果当前章节是“文献综述”且开题报告里有大段综述，可以考虑直接返回
        # 但为了保持文风统一，这里选择将开题报告作为 Context 传入 Prompt (Strategy I)，
        # 让 LLM 进行润色和扩写，而不是生硬的 Copy-Paste。
        
        # 2. 构建系统提示词 (包含开题报告约束)
        system_prompt = get_academic_thesis_prompt(
            target_words=word_count,
            ref_content_list=references,
            current_chapter_title=section_title,
            chapter_num=chapter_num,
            has_user_data=has_data,
            full_outline=full_outline_str,
            opening_report_data=opening_report # <--- 传入开题报告数据
        )

        user_prompt = f"请撰写章节：【{section_title}】\n要求字数：约 {word_count} 字。"
        
        # 3. 流式调用
        for chunk in self._call_llm_stream_with_client(self.main_client, system_prompt, user_prompt):
            yield chunk

    def _format_outline(self, chapters: List[Dict]) -> str:
        outline_lines = []
        for ch in chapters:
            title = ch.get('title', '未命名')
            outline_lines.append(f"- {title}")
        return "\n".join(outline_lines)

    def generate_stream(
            self, 
            task_id: str, 
            title: str, 
            chapters: List[Dict], 
            ref_domestic: str, 
            ref_foreign: str, 
            custom_data: str, 
            check_status_func, 
            initial_context: str = "", 
            extra_instructions: str = ""
            ) -> Generator[str, None, None]:
        
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
                    full_outline_str,
                    extra_instructions
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

    def _process_uploaded_files(self, files):
        """
        处理上传的文件列表：
        1. 文档类 (PDF, DOCX, TXT, CSV) -> 提取为文本字符串
        2. 图片类 -> 保留原始对象 (以便传给 Vision 模型)
        """
        if not files:
            return "", []

        extracted_text = []
        image_files = []

        for f in files:
            filename = f.get('name', '').lower()
            content_stream = f.get('content') # 这是一个 BytesIO 对象
            
            if not content_stream:
                continue
                
            # 重置指针
            content_stream.seek(0)

            # --- A. 图片处理 ---
            if filename.endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp')):
                # 将图片数据转为 base64 或直接传递流，取决于你的 _call_llm 实现
                # 这里我们传递原始 dict，让底层决定怎么处理
                image_files.append(f)
            
            # --- B. 文档处理 ---
            elif filename.endswith('.docx') and Document:
                try:
                    doc = Document(content_stream)
                    text = "\n".join([para.text for para in doc.paragraphs])
                    extracted_text.append(f"【参考文档：{filename}】\n{text}")
                except Exception as e:
                    print(f"Error parsing docx {filename}: {e}")
            
            elif filename.endswith('.pdf') and PdfReader:
                try:
                    reader = PdfReader(content_stream)
                    text = ""
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
                    extracted_text.append(f"【参考文档：{filename}】\n{text}")
                except Exception as e:
                    print(f"Error parsing pdf {filename}: {e}")
            
            elif filename.endswith(('.txt', '.csv', '.md')):
                try:
                    text = content_stream.read().decode('utf-8', errors='ignore')
                    extracted_text.append(f"【参考文档：{filename}】\n{text}")
                except Exception as e:
                    print(f"Error reading text {filename}: {e}")

        return "\n\n".join(extracted_text), image_files
    
    def rewrite_chapter(self, title: str, section_title: str, user_instruction: str, context: str, custom_data: str, original_content: str = "", files: list = None) -> str:
        # 【修改点 1】增加了 files 参数，默认为 None
        
        chapter_num = self._extract_chapter_num(section_title)
        
        # 【修改点 2】处理上传的文件
        # 提取文档文本 和 图片列表
        file_text_context, image_files = self._process_uploaded_files(files)
        
        # 【修改点 3】将提取的文档内容，合并到 custom_data 或 instruction 中
        # 这样 LLM 就能“读”到 Word/PDF 的内容了
        if file_text_context:
            custom_data = f"{custom_data}\n\n{file_text_context}"
            # 或者追加到 instruction，加强提示
            user_instruction += f"\n\n(请参考我上传的附件文档内容进行撰写)"

        # 1. 构建 Prompt
        sys_prompt = get_rewrite_prompt(title, section_title, user_instruction, context[-800:], custom_data, original_content, chapter_num)
        
        user_prompt = f"论文题目：{title}\n请修改章节：{section_title}\n用户的具体修改意见：{user_instruction}\n【最高指令】直接输出正文。如果需要绘图，请输出完整的 Markdown 代码块 (```python ... ```)，不要解释代码。"
        
        # 【修改点 4】调用 LLM 时传入 images
        # 注意：你需要确保 self._call_llm 方法能够接收 images 参数并传递给 GPT-4o/Claude
        if image_files:
            content = self._call_llm(sys_prompt, user_prompt, images=image_files)
        else:
            content = self._call_llm(sys_prompt, user_prompt)

        # 3. [Step 1] 清洗废话标题
        garbage_patterns = [
            r'^\s*(?:#+|\*\*|)?\s*(?:设置|定义|创建|绘制|添加|导入|准备)(?:绘图)?(?:风格|数据|变量|画布|条形图|折线图|饼图|统计图|图表|数值|标签|引用|相关库|代码).*?$',
            r'^\s*(?:#+|\*\*|)?\s*Python\s*代码(?:如下|示例)?[:：]?\s*$',
            r'^\s*(?:#+|\*\*|)?\s*代码如下[:：]?\s*$'
        ]
        for pat in garbage_patterns:
            content = re.sub(pat, '', content, flags=re.MULTILINE | re.IGNORECASE)

        # =========================================================
        # [Step 2] 核心修复：自动补全与宽容匹配
        # =========================================================
        
        # A. 自动闭合修复：如果代码块标记是奇数个，说明 LLM 没写完，强制补全
        if content.count('```') % 2 != 0:
            content += "\n```"

        # B. 宽容正则：允许 ```python, ``` python, 甚至不写 python 的 ``` 
        code_block_pattern = re.compile(r'(```\s*(?:python|py)?\s*[\s\S]*?```)', re.IGNORECASE)
        
        def image_replacer(match):
            full_block = match.group(1).strip()
            
            # 提取内部代码
            lines = full_block.split('\n')
            
            # 过滤掉第一行 (```xxx) 和最后一行 (```)
            code_lines = [line for line in lines if '```' not in line]
            
            if not code_lines: return "" # 空块
            
            code = '\n'.join(code_lines).strip()
            if not code: return ""

            try:
                # 执行绘图
                # 确保引入了 MarkdownToDocx 或相应的绘图工具
                img_buf = MarkdownToDocx.exec_python_plot(code)
                if img_buf:
                    b64_data = base64.b64encode(img_buf.getvalue()).decode('utf-8')
                    # 返回图片 HTML
                    return f'\n\n<div align="center" class="plot-container"><img src="data:image/png;base64,{b64_data}" style="max-width:85%; border:1px solid #eee; padding:5px; border-radius:4px;"></div>\n\n'
                else:
                    return "" 
            except Exception as e:
                print(f"Plot Logic Error: {e}")
                return ""

        # 执行替换
        new_content = code_block_pattern.sub(image_replacer, content)
        
        # [Step 3] 最后的扫尾
        new_content = re.sub(r'\n{3,}', '\n\n', new_content)

        return new_content.strip()

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