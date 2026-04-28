import logging


class SuppressAlertsAccessLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True

        if " /api/alerts" not in msg:
            return True
        try:
            parts = str(msg).split()
            status = None
            for tok in reversed(parts[-3:]):
                if tok.isdigit():
                    status = int(tok)
                    break
            if status is None:
                return True
        except Exception:
            return True
        return status >= 400
