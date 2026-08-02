"""JSON lines HTTP handler for Python logging."""

import json
import logging
import sys
import threading
import time
from datetime import UTC, datetime

import requests


class JsonLinesHandler(logging.Handler):
    """Ships log records to a JSON lines HTTP endpoint."""

    def __init__(
        self,
        endpoint: str = "http://localhost:9428/insert/jsonline",
        batch_size: int = 10,
        flush_interval: float = 1.0,
        headers: dict[str, str] | None = None,
    ):
        super().__init__()
        self.endpoint = endpoint
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.headers = headers or {}
        self._batch: list[str] = []
        self._last_flush: float = time.monotonic()
        self._lock = threading.RLock()

    def emit(self, record: logging.LogRecord) -> None:
        """Buffer a log record and flush if needed."""
        with self._lock:
            self._batch.append(self._format_entry(record))
            self._flush_if_needed()

    def _format_entry(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON lines entry."""
        entry = {
            "log": {"message": self.format(record)},
            "_time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "app": "waveshare-frame",
            "level": record.levelname.lower(),
        }
        return json.dumps(entry)

    def _flush_if_needed(self) -> None:
        """Flush the batch if size or time threshold is met."""
        now = time.monotonic()
        if len(self._batch) >= self.batch_size or (
            now - self._last_flush >= self.flush_interval and self._batch
        ):
            self._send_batch()

    def _send_batch(self) -> None:
        """Send buffered log entries to the JSON lines endpoint."""
        if not self._batch:
            return

        payload = "\n".join(self._batch)
        self._batch.clear()
        self._last_flush = time.monotonic()

        try:
            resp = requests.post(
                self.endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/stream+json",
                    **self.headers,
                },
                timeout=5,
                params={"_stream_fields": "app,level"},
            )
            if not resp.ok:
                print(
                    f"JSON lines: HTTP {resp.status_code} — {resp.text[:200]}",
                    file=sys.stderr,
                )
        except Exception as e:
            # Must not go through `logging` here: this handler may be attached to the
            # root logger, and emit() holds self._lock — routing back through logging
            # would re-enter emit() and deadlock on the non-reentrant lock.
            print(f"JSON lines: send failed — {e!r}", file=sys.stderr)

    def flush(self) -> None:
        """Flush any remaining buffered entries."""
        with self._lock:
            self._send_batch()

    def close(self) -> None:
        """Flush and close the handler."""
        try:
            self.flush()
        except Exception:
            pass
        super().close()
