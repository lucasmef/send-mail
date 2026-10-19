class QueueError(Exception):
    def __init__(self, code, message, exit_code=2, retryable=False, details=None):
        super().__init__(message)
        self.code, self.message = code, message
        self.exit_code, self.retryable, self.details = exit_code, retryable, details

    def as_dict(self):
        result = dict(code=self.code, message=self.message, retryable=self.retryable)
        if self.details is not None:
            result["details"] = self.details
        return result
