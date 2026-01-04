
import re
import json
import time
from openai import OpenAI
from typing import Dict, List, Generator
from .reference import ReferenceManager
from .word import TextCleaner
from .prompts import get_rewrite_prompt, get_word_distribution_prompt, get_academic_thesis_prompt
import concurrent.futures

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