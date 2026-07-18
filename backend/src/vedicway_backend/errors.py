from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class DomainError(Exception):
    code: str
    message: str
    recoverable: bool = True
    status_code: int = 422
    detail: dict[str, object] | None = None

    def as_payload(self, trace_id: str) -> dict[str, object]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "recoverable": self.recoverable,
                "trace_id": trace_id,
                "detail": self.detail or {},
            }
        }
