import threading
from concurrent.futures import ThreadPoolExecutor
from core.engine.profile_worker import ProfileWorker

class AutomationEngine:
    def __init__(self, max_workers=3):
        self.max_workers = max_workers
        self.executor = None
        self.workers = []
        self.futures = []
        self._is_running = False
        self._lock = threading.Lock()

    def start(self, task_type, posts, flow_wrapper_function, logger_callback, completion_callback, master_ui_context=None, on_finished_callback=None):
        with self._lock:
            if self._is_running:
                logger_callback("Engine is already running.")
                return False
            self._is_running = True
            self.workers = []
            self.futures = []
            self.executor = ThreadPoolExecutor(max_workers=self.max_workers)

        logger_callback(f"--- Starting Automation Engine ({task_type}) with {self.max_workers} concurrent profiles ---")

        def task_completion_hook(post, success, result_msg=""):
            try:
                completion_callback(post, success, result_msg)
            except TypeError:
                completion_callback(post, success)

        for post in posts:
            worker = ProfileWorker(
                task_type=task_type,
                post_data=post,
                flow_function=flow_wrapper_function,
                logger_callback=logger_callback,
                completion_callback=task_completion_hook,
                master_ui_context=master_ui_context
            )
            self.workers.append(worker)
            future = self.executor.submit(worker.run)
            self.futures.append(future)

        def monitor_completion():
            # Wait for all submitted tasks to complete
            if self.executor:
                self.executor.shutdown(wait=True)
            
            with self._lock:
                self._is_running = False
                self.workers = []
                self.futures = []
                self.executor = None
            
            logger_callback("--- Automation Engine Finished ---")
            if on_finished_callback:
                on_finished_callback()

        threading.Thread(target=monitor_completion, daemon=True).start()
        return True

    def stop(self, logger_callback=print):
        """Signals all workers to stop and cancels pending futures."""
        with self._lock:
            if not self._is_running:
                return
            logger_callback("Stopping Automation Engine... signaling workers.")
            
            # Cancel any futures that haven't started yet and signal running ones
            for worker, future in zip(self.workers, self.futures):
                if future.cancel():
                    # Task was successfully cancelled before starting, manually trigger callback
                    try:
                        worker.completion_callback(worker.post, False, "Cancelled before starting")
                    except TypeError:
                        # Fallback for old signature
                        worker.completion_callback(worker.post, False)
                else:
                    worker.stop()
                
            # Note: We do NOT call executor.shutdown() here.
            # The monitor_completion thread is already waiting on it and will
            # cleanly shut it down once the workers finish their graceful exit.
