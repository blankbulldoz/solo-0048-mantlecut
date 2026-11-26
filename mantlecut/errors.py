class Rejected(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code = code
        self.status = status


def conflict(code: str, message: str):
    return Rejected(code, message, 409)


def missing(label: str):
    return Rejected("not_found", f"未找到{label}", 404)
