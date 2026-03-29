"""Queue manager for controlling concurrent downloads"""

from collections import deque
from PySide6.QtCore import QObject, Signal


class DownloadQueueManager(QObject):
    task_added = Signal(str)
    task_completed = Signal(str)
    
    def __init__(self, max_concurrent=3):
        super().__init__()
        self.max_concurrent = max_concurrent
        self.queue = deque()
        self.active_tasks = {}
        self.all_tasks = {}
        
    def set_max_concurrent(self, max_concurrent):
        self.max_concurrent = max_concurrent
        
    def add_task(self, task_id, worker):
        self.all_tasks[task_id] = worker
        if len(self.active_tasks) < self.max_concurrent:
            self._start_task(task_id, worker)
        else:
            self.queue.append((task_id, worker))
            
    def _start_task(self, task_id, worker):
        self.active_tasks[task_id] = worker
        # Use Qt.UniqueConnection to prevent duplicate signal connections
        # if a worker is somehow re-started
        worker.finished.connect(
            lambda _tid, _ok, _msg, tid=task_id: self._on_task_finished(tid)
        )
        worker.start()
        self.task_added.emit(task_id)

    def _on_task_finished(self, task_id):
        self.active_tasks.pop(task_id, None)
        self.all_tasks.pop(task_id, None)
        self.task_completed.emit(task_id)

        # Advance queue — skip any cancelled workers
        while self.queue:
            next_id, next_worker = self.queue.popleft()
            if not next_worker._cancelled:
                self._start_task(next_id, next_worker)
                break
            
    def pause_all(self):
        for worker in self.active_tasks.values():
            worker.pause()
        for _, worker in self.queue:
            worker.pause()
            
    def resume_all(self):
        for worker in self.active_tasks.values():
            worker.resume()
        for _, worker in self.queue:
            worker.resume()
            
    def cancel_all(self):
        for worker in list(self.active_tasks.values()):
            worker.cancel()
        for _, worker in list(self.queue):
            worker.cancel()
        self.queue.clear()
        self.active_tasks.clear()
        self.all_tasks.clear()
        
    def get_active_count(self):
        return len(self.active_tasks)
        
    def get_queued_count(self):
        return len(self.queue)
