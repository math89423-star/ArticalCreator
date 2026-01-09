# utils/worker.py
import time
import json
from utils.state import task_manager
from utils.files import extract_file_content

def background_worker(writer, task_id, title, chapters, ref_domestic, ref_foreign, text_custom_data, raw_files_data, check_status_func, initial_context, user_id, extra_instructions):
    try:
        # 1. 在后台线程中进行文件解析
        final_custom_data = text_custom_data
        
        if raw_files_data:
            task_manager.append_event(user_id, task_id, f"data: {json.dumps({'type': 'log', 'msg': '📂 正在后台解析上传的文件...'})}\n\n")
            
            file_extracted_text = ""
            for file_info in raw_files_data:
                time.sleep(0.01) # 释放 GIL
                
                try:
                    extracted = extract_file_content(file_info['content'], file_info['name'])
                    file_extracted_text += extracted + "\n\n"
                except Exception as e:
                    file_extracted_text += f"\n文件 {file_info['name']} 解析失败: {e}\n"
            
            final_custom_data = text_custom_data + "\n" + file_extracted_text
            task_manager.append_event(user_id, task_id, f"data: {json.dumps({'type': 'log', 'msg': '✅ 文件解析完成，开始生成...'})}\n\n")

        # 2. 执行生成器
        generator = writer.generate_stream(
            task_id, title, chapters, ref_domestic, ref_foreign, final_custom_data, check_status_func, initial_context, extra_instructions
        )
        
        # 3. 逐条消费
        for chunk in generator:
            if check_status_func() == 'stopped':
                print(f"[Worker] 线程检测到停止信号，正在退出: {task_id}")
                return
            task_manager.append_event(user_id, task_id, chunk)
            time.sleep(0.005) 
            
    except Exception as e:
        error_msg = json.dumps({'type': 'log', 'msg': f'❌ 后台任务异常: {str(e)}'})
        task_manager.append_event(user_id, task_id, f"data: {error_msg}\n\n")
    finally:
        current_status = task_manager.get_status(user_id, task_id)
        if current_status == 'running':
            task_manager.set_status(user_id, task_id, 'completed')