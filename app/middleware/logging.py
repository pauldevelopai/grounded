"""Structured logging middleware with request tracking."""
import logging
import json
import time
import uuid
from typing import Callable
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.settings import settings


class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add request_id if present
        if hasattr(record, 'request_id'):
            log_data['request_id'] = record.request_id

        # Add extra fields
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all requests with structured JSON logs and request IDs."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logging.getLogger("app.requests")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log details."""
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Start timing
        start_time = time.time()

        # Log request start
        extra = {
            'request_id': request_id,
            'extra_fields': {
                'method': request.method,
                'path': request.url.path,
                'query_params': str(request.query_params),
                'client_ip': request.client.host if request.client else None,
            }
        }
        self.logger.info(f"Request started: {request.method} {request.url.path}", extra=extra)

        # Process request
        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log request completion
            extra['extra_fields']['status_code'] = response.status_code
            extra['extra_fields']['duration_ms'] = round(duration_ms, 2)

            self.logger.info(
                f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                extra=extra
            )

            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            # Log error
            duration_ms = (time.time() - start_time) * 1000
            extra['extra_fields']['duration_ms'] = round(duration_ms, 2)
            extra['extra_fields']['error'] = str(e)

            self.logger.error(
                f"Request failed: {request.method} {request.url.path} - {e}",
                extra=extra,
                exc_info=True
            )
            raise


def setup_logging():
    """Configure logging based on settings."""
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # Remove existing handlers
    root_logger.handlers.clear()

    # Create console handler
    console_handler = logging.StreamHandler()

    if settings.LOG_FORMAT == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        # Text format for development
        console_handler.setFormatter(
            logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        )

    root_logger.addHandler(console_handler)

    # Optional file handler
    if settings.LOG_FILE:
        file_handler = logging.FileHandler(settings.LOG_FILE)
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    logging.info(f"Logging configured: level={settings.LOG_LEVEL}, format={settings.LOG_FORMAT}")
