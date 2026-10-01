
class AutomationError(Exception):
    """Base class for automation exceptions."""
    pass

class RetryableError(AutomationError):
    """Errors that should trigger a retry (e.g., timeouts, network drops)."""
    pass

class PermanentError(AutomationError):
    """Errors that should permanently fail the row (e.g., bad config, missing fields)."""
    pass

class AutomationStopped(AutomationError):
    """Raised when the user manually stops the automation."""
    pass

