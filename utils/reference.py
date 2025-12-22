# ==============================================================================
# 引用管理器
# ==============================================================================
import re
import math
from typing import List, Dict, Tuple


class ReferenceManager:
    def __init__(self, raw_references: str):
        raw_lines = [r.strip() for r in raw_references.split('\n') if r.strip()]
        self.all_refs = []
        clean_pattern = re.compile(r'^(\[\d+\]|\d+\.|（\d+）|\(\d+\))\s*')
        for line in raw_lines:
            cleaned_line = clean_pattern.sub('', line)
            self.all_refs.append(cleaned_line)
        self.current_chapter_refs = []

    def is_chinese(self, text: str) -> bool:
        return bool(re.search(r'[\u4e00-\u9fa5]', text))

    def distribute_references_smart(self, chapters: List[Dict]) -> Dict[int, List[Tuple[int, str]]]:
        if not self.all_refs: return {}
        cn_refs = [ (i+1, r) for i, r in enumerate(self.all_refs) if self.is_chinese(r) ]
        en_refs = [ (i+1, r) for i, r in enumerate(self.all_refs) if not self.is_chinese(r) ]

        domestic_idxs = []
        foreign_idxs = []
        general_idxs = []
        last_content_idx = -1

        for i, chapter in enumerate(chapters):
            if chapter.get('is_parent'): continue
            title = chapter['title']
            
            if "参考文献" not in title and "致谢" not in title and "摘要" not in title:
                 last_content_idx = i

            if any(k in title for k in ["现状", "综述", "Review", "Status", "背景"]):
                if "国内" in title or "我国" in title or "China" in title:
                    domestic_idxs.append(i)
                elif "国外" in title or "国际" in title or "Foreign" in title:
                    foreign_idxs.append(i)
                else:
                    general_idxs.append(i)

        allocation = {} 
        def assign_chunks(refs_list, target_idxs):
            if not target_idxs: return refs_list
            if not refs_list: return []
            chunk_size = math.ceil(len(refs_list) / len(target_idxs))
            for k, idx in enumerate(target_idxs):
                start = k * chunk_size
                chunk = refs_list[start : start + chunk_size]
                if not chunk: continue
                if idx not in allocation: allocation[idx] = []
                allocation[idx].extend(chunk)
            return []

        rem_cn = assign_chunks(cn_refs, domestic_idxs)
        rem_en = assign_chunks(en_refs, foreign_idxs)
        rem_all = rem_cn + rem_en
        rem_all.sort(key=lambda x: x[0])
        rem_final = assign_chunks(rem_all, general_idxs)

        if rem_final and last_content_idx != -1:
             if last_content_idx not in allocation: allocation[last_content_idx] = []
             allocation[last_content_idx].extend(rem_final)

        for idx in allocation:
            allocation[idx].sort(key=lambda x: x[0])
        return allocation

    def set_current_chapter_refs(self, refs: List[Tuple[int, str]]):
        self.current_chapter_refs = list(refs) 

    def process_text_deterministic(self, text: str) -> str:
        result_text = ""
        parts = text.split('[REF]')
        for i, part in enumerate(parts):
            result_text += part
            if i < len(parts) - 1:
                if self.current_chapter_refs:
                    global_id, _ = self.current_chapter_refs.pop(0)
                    result_text += f"[{global_id}]"
        
        if self.current_chapter_refs:
            result_text += "\n\n"
            remaining_ids = []
            while self.current_chapter_refs:
                global_id, _ = self.current_chapter_refs.pop(0)
                remaining_ids.append(f"[{global_id}]")
            result_text += f"此外，相关研究还涵盖了多方面的探索{ ''.join(remaining_ids) }。"
        return result_text

    def generate_bibliography(self) -> str:
        if not self.all_refs: return ""
        res = "## 参考文献\n\n"
        for i, ref_content in enumerate(self.all_refs):
            res += f"[{i+1}] {ref_content}\n\n"
        return res
