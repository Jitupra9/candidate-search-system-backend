"""
Central Logging Setup
======================
Development : colored console, DEBUG level
Production  : JSON structured, INFO level

Call setup_logging() once at app startup in main.py and celery_app.py.
All modules use: logger = logging.getLogger(__name__)
"""
import logging
import sys
from app.core.config import settings

_LEVEL = logging.DEBUG if settings.APP_ENV == "development" else logging.INFO


class _ColorFormatter(logging.Formatter):
    COLORS = {
        logging.DEBUG:    "\033[36m",   # cyan
        logging.INFO:     "\033[32m",   # green
        logging.WARNING:  "\033[33m",   # yellow
        logging.ERROR:    "\033[31m",   # red
        logging.CRITICAL: "\033[35m",   # magenta
    }
    RESET = "\033[0m"
    FMT   = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelno, self.RESET)
        fmt   = logging.Formatter(f"{color}{self.FMT}{self.RESET}", datefmt="%H:%M:%S")
        return fmt.format(record)


class _JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        import json
        payload = {
            "time":    self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":   record.levelname,
            "logger":  record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _ColorFormatter() if settings.APP_ENV == "development" else _JSONFormatter()
    )

    root = logging.getLogger()
    root.setLevel(_LEVEL)
    root.handlers.clear()
    root.addHandler(handler)

    # silence noisy third-party loggers
    for name in ("httpx", "httpcore", "uvicorn.access", "chromadb",
                 "langchain", "openai", "anthropic", "groq"):
        logging.getLogger(name).setLevel(logging.WARNING)

    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    logging.info("logging ready — env=%s level=%s", settings.APP_ENV, logging.getLevelName(_LEVEL))
