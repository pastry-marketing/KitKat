import threading
import time
from core.engine.state_machine import AutomationState
from core.engine.exceptions import RetryableError, PermanentError, AutomationStopped
from core.engine.retry_manager import RetryManager
from core.services.sheets_service import claim_row, update_row_status, update_column_value
from core.automation.browser_manager import start_profile, stop_profile, update_profile_proxy
from core.automation.profile_builder import get_val

class ProfileWorker:
    def __init__(self, task_type, post_data, flow_function, logger_callback, completion_callback, master_ui_context=None, progress_callback=None):
        self.task_type = task_type
        self.post = post_data
        self.flow_function = flow_function
        self.logger_callback = logger_callback
        self.completion_callback = completion_callback
        self.master_ui_context = master_ui_context
        self.progress_callback = progress_callback
        self.state = AutomationState.QUEUED
        self._stop_event = threading.Event()
        self.retry_manager = RetryManager(max_attempts=3, backoff_seconds=5.0, logger_callback=self.log)
        
    def log(self, msg):
        self.logger_callback(f"[{get_val(self.post, 'profile name', 'name', 'profile') or 'Unknown'}] {msg}")

    def update_state(self, new_state, result_msg=""):
        self.state = new_state
        self.log(f"Status -> {new_state.value}")
        if result_msg:
            self.log(result_msg)
        if self.progress_callback:
            self.progress_callback(new_state.value, result_msg)

    def stop(self):
        self._stop_event.set()

    def _log_failure(self, profile_id, row, exc_type, msg):
        import datetime
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"\n--- FAILURE DIAGNOSTICS ---\nTimestamp: {ts}\nProfile: {get_val(self.post, 'profile name', 'name', 'profile')}\nProfile ID: {profile_id}\nRow: {row}\nStage: {self.state.name}\nException type: {exc_type}\nError: {msg}\n---------------------------")


    def _check_stop(self):
        if self._stop_event.is_set():
            raise AutomationStopped("User manually stopped automation.")

    def run(self):
        profile_name_or_id = get_val(self.post, "profile name", "name", "profile")
        profile_id = self.post.get("id") if self.post.get("id") else profile_name_or_id
        row_number = self.post.get("rowNumber")

        # 1. Claim the row
        self.update_state(AutomationState.CLAIMED)
        success, msg = claim_row(self.task_type, row_number)
        if not success:
            self.update_state(AutomationState.FAILED_PERMANENT, f"Could not claim row: {msg}")
            update_row_status(self.task_type, row_number, "Failed", f"Row claimed by another process: {msg}")
            self.completion_callback(self.post, False)
            return

        def _single_attempt():
            self._check_stop()

            # Proxy Update
            new_proxy_str = get_val(self.post, "proxy", "proxy string")
            if new_proxy_str and str(new_proxy_str).lower() != "n/a":
                self.log("Updating proxy before launch...")
                upd_ok, upd_msg = update_profile_proxy(profile_id, new_proxy_str)
                if upd_ok:
                    self.log("Proxy updated successfully.")
                else:
                    # Treat proxy failure as permanent to avoid wasting time on bad IPs
                    raise PermanentError(f"Failed to update proxy: {upd_msg}")

            # Start Profile
            self.update_state(AutomationState.PROFILE_STARTING)
            
            def _auto_resolve_duplicates(master, identifier, matches):
                """Auto-pick the first matching profile when duplicates are found."""
                return matches[0]['id'] if matches else None
                
            started, data = start_profile(profile_id, duplicate_resolver=_auto_resolve_duplicates, master=None)
            
            if not started:
                raise RetryableError(f"Failed to start profile: {data}")

            self._check_stop()

            # Extract CDP
            debug_url = data.get("url") if isinstance(data, dict) else ""
            if not debug_url and "puppeteerUrl" in data: debug_url = data.get("puppeteerUrl")
            if not debug_url and "webSocketDebuggerUrl" in data: debug_url = data.get("webSocketDebuggerUrl")
            if not debug_url: debug_url = f"http://127.0.0.1:{data.get('port')}" if isinstance(data, dict) and data.get("port") else ""
            if debug_url and not debug_url.startswith("http") and not debug_url.startswith("ws"):
                debug_url = f"ws://{debug_url}"

            # Run Flow
            self.update_state(AutomationState.CDP_CONNECTING)
            
            # The flow_wrapper needs to accept stop_event and state_callback if it wants to be smart
            # We will pass kwargs down
            status, result_msg = self.flow_function(
                debug_url=debug_url, 
                post=self.post, 
                logger=self.log,
                state_callback=self.update_state,
                stop_event=self._stop_event
            )
            
            if status == "FOUND" or status == True:
                return True, result_msg
            else:
                # Flow function itself might return False, result_msg
                # We can treat soft failures as PermanentError unless the flow raises RetryableError itself.
                raise PermanentError(result_msg)

        # Execute with retries
        final_status = False
        final_result_msg = ""
        try:
            success, result_msg = self.retry_manager.execute_with_retry(_single_attempt, stop_event=self._stop_event)
            final_result_msg = result_msg
            self.update_state(AutomationState.SUCCESS, f"Link -> {result_msg}")
            
            if self.task_type in ["Auto Posting", "Auto Listing", "Auto Random Posting"] and str(result_msg).startswith("http"):
                update_column_value(self.task_type, row_number, "Post link", str(result_msg))
                update_row_status(self.task_type, row_number, "Posted")
            else:
                update_row_status(self.task_type, row_number, "Posted", f"Link: {result_msg}")
                
            final_status = True
        except AutomationStopped:
            final_result_msg = "User manually stopped automation."
            self.update_state(AutomationState.STOPPED)
            update_row_status(self.task_type, row_number, "Failed (Stopped)")
        except PermanentError as e:
            final_result_msg = str(e)
            self._log_failure(profile_id, row_number, "PermanentError", str(e))
            self.update_state(AutomationState.FAILED_PERMANENT, str(e))
            update_row_status(self.task_type, row_number, f"Failed: {str(e)}")
        except RetryableError as e:
            final_result_msg = f"Max retries reached: {str(e)}"
            self._log_failure(profile_id, row_number, "RetryableError (Max Retries)", str(e))
            self.update_state(AutomationState.FAILED_RETRYABLE, f"Max retries reached: {str(e)}")
            update_row_status(self.task_type, row_number, f"Failed (Timeout/Retryable): {str(e)}")
        except Exception as e:
            final_result_msg = f"Unexpected Exception: {str(e)}"
            self._log_failure(profile_id, row_number, type(e).__name__, str(e))
            self.update_state(AutomationState.FAILED_PERMANENT, f"Unexpected Exception: {str(e)}")
            update_row_status(self.task_type, row_number, f"Failed: {str(e)}")
        finally:
            self.log("Stopping profile...")
            stop_profile(profile_id)
            self._stop_event.wait(3)
            self.completion_callback(self.post, final_status, final_result_msg)


