
import time
from core.engine.exceptions import RetryableError, PermanentError, AutomationStopped

class RetryManager:
    def __init__(self, max_attempts=3, backoff_seconds=3.0, logger_callback=None):
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        self.log = logger_callback or print

    def execute_with_retry(self, func, *args, stop_event=None, **kwargs):
        """
        Executes a function and retries on RetryableError.
        Raises PermanentError or AutomationStopped immediately.
        """
        attempt = 1
        while attempt <= self.max_attempts:
            if stop_event and stop_event.is_set():
                self.log("Stop requested before attempt. Aborting.")
                raise AutomationStopped("User manually stopped automation.")
                
            try:
                return func(*args, **kwargs)
            except AutomationStopped as e:
                self.log(f"Stop requested. Aborting.")
                raise e
            except PermanentError as e:
                self.log(f"Permanent error encountered: {str(e)}")
                raise e
            except RetryableError as e:
                if attempt < self.max_attempts:
                    self.log(f"Retryable error (Attempt {attempt}/{self.max_attempts}): {str(e)}. Retrying in {self.backoff_seconds}s...")
                    if stop_event is not None:
                        if stop_event.wait(self.backoff_seconds):
                            raise AutomationStopped("User manually stopped automation.")
                    else:
                        time.sleep(self.backoff_seconds)
                    attempt += 1
                else:
                    self.log(f"Max retries reached ({self.max_attempts}). Failing.")
                    raise e
            except Exception as e:
                # Unclassified exceptions are treated as permanent to be safe, 
                # or we can treat them as retryable. Let's treat unknown Playwright errors as retryable?
                # Actually, standard best practice: unexpected = permanent, unless explicitly caught and wrapped.
                self.log(f"Unhandled exception: {str(e)}. Failing permanently.")
                raise PermanentError(f"Unhandled error: {str(e)}")

