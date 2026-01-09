import threading
import time

class TaskManager:
    def __init__(self):
        # 使用 RLock 确保线程安全
        self._lock = threading.RLock()
        # 结构: { user_id: { task_id: { 'status': 'running', ... } } }
        self._user_tasks = {} 
        # [新增] 用于追踪正在运行的线程，以便取消
        self._active_threads = {}


    def start_task(self, user_id, task_id):
        """初始化任务状态"""
        with self._lock:
            # [核心修复] 如果该任务已在运行，先标记为 stopped，迫使旧线程退出
            # 注意：这里只是软停止，依赖 background_worker 内部检查 check_status_func
            if user_id in self._user_tasks and task_id in self._user_tasks[user_id]:
                if self._user_tasks[user_id][task_id]['status'] == 'running':
                    print(f"[System] ⚠️ 检测到任务 {task_id} 正在运行，正在强制重启...")
                    self._user_tasks[user_id][task_id]['status'] = 'stopped'
                    # 给旧线程一点时间退出（可选）
                    time.sleep(0.5)

            if user_id not in self._user_tasks:
                self._user_tasks[user_id] = {}
            
            # 初始化
            self._user_tasks[user_id][task_id] = {
                'status': 'running',
                'events': [],      
                'created_at': time.time(),
                'last_read_idx': 0 
            }
            print(f"[System] 任务启动: User={user_id}, Task={task_id}")

    def append_event(self, user_id, task_id, event_data):
        """写入消息"""
        with self._lock:
            if user_id in self._user_tasks and task_id in self._user_tasks[user_id]:
                self._user_tasks[user_id][task_id]['events'].append(event_data)

    def get_events_from(self, user_id, task_id, start_index):
        """读取消息"""
        with self._lock:
            # 严格检查层级，防止报错
            if user_id not in self._user_tasks or task_id not in self._user_tasks[user_id]:
                return [], 'stopped'
            
            task = self._user_tasks[user_id][task_id]
            events_len = len(task['events'])
            
            # 增量读取
            if start_index >= events_len:
                return [], task['status']
                
            new_events = task['events'][start_index:]
            return new_events, task['status']

    def set_status(self, user_id, task_id, status):
        """设置状态 (带日志)"""
        with self._lock:
            if user_id in self._user_tasks and task_id in self._user_tasks[user_id]:
                old_status = self._user_tasks[user_id][task_id]['status']
                self._user_tasks[user_id][task_id]['status'] = status
                print(f"[Control] 状态变更: User={user_id}, Task={task_id} | {old_status} -> {status}")
            else:
                print(f"[Control] ⚠️ 尝试修改不存在的任务: User={user_id}, Task={task_id}")

    def get_status(self, user_id, task_id):
        """获取状态 (默认 stopped 以防万一)"""
        with self._lock:
            if user_id not in self._user_tasks:
                return 'stopped'
            if task_id not in self._user_tasks[user_id]:
                return 'stopped'
            return self._user_tasks[user_id][task_id]['status']