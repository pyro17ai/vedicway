from __future__ import annotations

import argparse
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from .calculator import calculate_expert_extended, calculate_extended, calculate_instant
from .errors import DomainError
from .evidence import compile_evidence
from .interpretation import InterpretationProvider, provider_from_environment, validate_bundle
from .observability import Metrics
from .pdf import PdfRenderer
from .schemas import ChartSnapshot, JobStatus, SectionStatus, section_model
from .store import Store


@dataclass(slots=True)
class WorkerOutcome:
    job_id: str | None
    handled: bool


class ChartWorker:
    """Durable queue consumer with one calculation critical section per process.

    PyJHora changes module-level calculation state while applying ayanamsa. A process
    owns a single critical section, and deployment starts separate worker processes.
    """

    _calculation_lock = threading.Lock()

    def __init__(self, store: Store, provider: InterpretationProvider | None = None, metrics: Metrics | None = None) -> None:
        self.store = store
        self.provider = provider or provider_from_environment()
        self.pdf_renderer = PdfRenderer(store.reports_dir)
        self.metrics = metrics

    def process_once(self) -> WorkerOutcome:
        job = self.store.claim_next_job()
        if not job:
            return WorkerOutcome(job_id=None, handled=False)
        try:
            if self.metrics:
                with self.metrics.time("job_duration_seconds", {"job_type": str(job["job_type"])}):
                    self._dispatch(job)
            else:
                self._dispatch(job)
            if self.metrics:
                self.metrics.increment("job_success_total", {"job_type": str(job["job_type"])})
        except DomainError as exc:
            retryable = exc.recoverable and int(job["attempts"]) < 3
            status = JobStatus.FAILED_RETRYABLE if retryable else JobStatus.FAILED_TERMINAL
            self.store.update_job_status(job["id"], status, {"code": exc.code, "message": exc.message, "recoverable": retryable})
            if job["job_type"] == "instant_v1":
                self.store.mark_chart_status(job["chart_id"], "failed")
            self.store.emit(
                job["chart_id"],
                "job.failed",
                {"job_type": job["job_type"], "code": exc.code, "recoverable": retryable},
            )
            if self.metrics:
                self.metrics.increment("job_failure_total", {"job_type": str(job["job_type"]), "code": exc.code})
        except Exception:
            self.store.update_job_status(
                job["id"], JobStatus.FAILED_RETRYABLE,
                {"code": "UNEXPECTED_WORKER_FAILURE", "message": "Расчёт временно недоступен", "recoverable": True},
            )
            self.store.emit(
                job["chart_id"], "job.failed",
                {"job_type": job["job_type"], "code": "UNEXPECTED_WORKER_FAILURE", "recoverable": True},
            )
            if self.metrics:
                self.metrics.increment("job_failure_total", {"job_type": str(job["job_type"]), "code": "UNEXPECTED_WORKER_FAILURE"})
        return WorkerOutcome(job_id=str(job["id"]), handled=True)

    def drain(self, limit: int = 16) -> int:
        count = 0
        while count < limit:
            outcome = self.process_once()
            if not outcome.handled:
                break
            count += 1
        return count

    def _dispatch(self, job: dict[str, Any]) -> None:
        handlers = {
            "instant_v1": self._instant,
            "evidence_free_v1": self._evidence,
            "expert_extended_v1": self._expert_extended,
            "interpretation_free_v1": self._free_interpretation,
            "paid_report_v1": self._paid_report,
            "pdf_v1": self._pdf,
        }
        handler = handlers.get(str(job["job_type"]))
        if not handler:
            raise DomainError("JOB_UNKNOWN", "Неизвестный тип фоновой задачи", recoverable=False)
        handler(job)
        self.store.update_job_status(job["id"], JobStatus.SUCCEEDED)

    def _instant(self, job: dict[str, Any]) -> None:
        chart_id = str(job["chart_id"])
        self.store.emit(chart_id, "calculation.started", {"profile": "instant_v1"})
        birth = self.store.get_birth(chart_id)
        started = time.perf_counter()
        with self._calculation_lock:
            snapshot = calculate_instant(birth, chart_id)
        if self.metrics:
            self.metrics.observe("instant_d1_seconds", time.perf_counter() - started)
        self.store.commit_snapshot_events(
            chart_id,
            snapshot,
            [("d1.ready", {"section": "d1", "snapshot_id": snapshot.snapshot_id})],
        )
        self.store.enqueue_job(chart_id, "evidence_free_v1", priority=80)

    def _evidence(self, job: dict[str, Any]) -> None:
        chart_id = str(job["chart_id"])
        snapshot = self.store.get_snapshot(chart_id)
        if snapshot is None:
            raise DomainError("SNAPSHOT_MISSING", "Основная карта ещё не готова", recoverable=True)
        birth = self.store.get_birth(chart_id)
        with self._calculation_lock:
            extended = calculate_extended(birth, snapshot)
        extended["vargas"] = section_model(
            "vargas",
            SectionStatus.READY,
            {"charts": {key: extended[key]["data"] for key in ("D2", "D4", "D9", "D10", "D12", "D24")}},
        )
        data = snapshot.model_dump(mode="json")
        data["sections"].update(extended)
        enriched = ChartSnapshot.model_validate(data)
        facts, packets = compile_evidence(enriched)
        coverage = {packet.slug.value: packet.coverage.value for packet in packets}
        self.store.commit_evidence_events(
            chart_id,
            enriched,
            [fact.model_dump(mode="json") for fact in facts],
            [packet.model_dump(mode="json") for packet in packets],
            [("evidence.ready", {"coverage": coverage})],
        )
        self.store.enqueue_job(chart_id, "interpretation_free_v1", priority=70)

    def _load_evidence(self, chart_id: str):
        value = self.store.get_evidence(chart_id)
        snapshot = self.store.get_snapshot(chart_id)
        if not value or snapshot is None:
            raise DomainError("EVIDENCE_MISSING", "Расчётные основания ещё не готовы", recoverable=True)
        from .schemas import DomainEvidencePacket, EvidenceFact

        facts = [EvidenceFact.model_validate(item) for item in value["facts"]]
        packets = [DomainEvidencePacket.model_validate(item) for item in value["packets"]]
        return snapshot, facts, packets

    def _expert_extended(self, job: dict[str, Any]) -> None:
        chart_id = str(job["chart_id"])
        snapshot = self.store.get_snapshot(chart_id)
        if snapshot is None:
            raise DomainError("SNAPSHOT_MISSING", "Основная карта ещё не готова", recoverable=True)
        birth = self.store.get_birth(chart_id)
        with self._calculation_lock:
            extended = calculate_expert_extended(birth, snapshot)
        data = snapshot.model_dump(mode="json")
        data["sections"].update(extended)
        enriched = ChartSnapshot.model_validate(data)
        self.store.commit_snapshot_events(
            chart_id,
            enriched,
            [("calculation.partial", {"section": "expert_extended", "status": "ready"})],
        )

    def _free_interpretation(self, job: dict[str, Any]) -> None:
        chart_id = str(job["chart_id"])
        snapshot, facts, packets = self._load_evidence(chart_id)
        self.store.emit(chart_id, "interpretation.started", {"stage": "free"})
        run_id = self._start_agent_run(chart_id, job, facts, packets, paid=False)
        try:
            bundle = self.provider.generate(snapshot.snapshot_id, facts, packets, paid=False)
            self.store.emit(chart_id, "interpretation.validating", {"attempt": int(job["attempts"])})
            validated = validate_bundle(bundle, snapshot.snapshot_id, facts, packets, paid=False)
        except Exception:
            self.store.finish_agent_run(run_id, "failed")
            raise
        self.store.finish_agent_run(run_id, "succeeded", self._bundle_checksum(validated))
        self.store.commit_bundle_events(
            chart_id,
            validated,
            paid=False,
            events=[
                ("interpretation.ready", {"bundle_version": validated.schema_version}),
                ("questions.ready", {"count": len(validated.questions)}),
            ],
        )

    def _paid_report(self, job: dict[str, Any]) -> None:
        chart_id = str(job["chart_id"])
        if not self.store.has_entitlement(chart_id):
            raise DomainError("ENTITLEMENT_REQUIRED", "Полный отчёт доступен после подтверждения оплаты", recoverable=False, status_code=403)
        snapshot, facts, packets = self._load_evidence(chart_id)
        self.store.emit(chart_id, "report.started", {"sections_total": len(packets)})
        run_id = self._start_agent_run(chart_id, job, facts, packets, paid=True)
        try:
            bundle = self.provider.generate(snapshot.snapshot_id, facts, packets, paid=True)
            self.store.emit(chart_id, "interpretation.validating", {"attempt": int(job["attempts"])})
            validated = validate_bundle(bundle, snapshot.snapshot_id, facts, packets, paid=True)
        except Exception:
            self.store.finish_agent_run(run_id, "failed")
            raise
        self.store.finish_agent_run(run_id, "succeeded", self._bundle_checksum(validated))
        events: list[tuple[str, dict[str, Any]]] = []
        for index, domain in enumerate(validated.domains, start=1):
            events.append(
                ("report.section_ready", {"domain": domain.slug.value, "completed": index, "total": len(validated.domains)})
            )
        events.append(("report.ready", {"report_version": validated.schema_version}))
        self.store.commit_bundle_events(chart_id, validated, paid=True, events=events)
        self.store.enqueue_job(chart_id, "pdf_v1", priority=60)

    def _start_agent_run(self, chart_id: str, job: dict[str, Any], facts, packets, paid: bool) -> str:
        payload = {
            "facts": [fact.model_dump(mode="json") for fact in facts],
            "packets": [packet.model_dump(mode="json") for packet in packets],
            "access": "paid_full" if paid else "free_summary",
        }
        input_checksum = f"sha256:{hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()}"
        return self.store.start_agent_run(
            chart_id,
            str(job["id"]),
            type(self.provider).__name__,
            "interpretation.paid.v1" if paid else "interpretation.free.v1",
            input_checksum,
        )

    @staticmethod
    def _bundle_checksum(bundle) -> str:
        raw = json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        return f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    def _pdf(self, job: dict[str, Any]) -> None:
        chart_id = str(job["chart_id"])
        if not self.store.has_entitlement(chart_id):
            raise DomainError("ENTITLEMENT_REQUIRED", "PDF доступен после подтверждения оплаты", recoverable=False, status_code=403)
        snapshot = self.store.get_snapshot(chart_id)
        bundle = self.store.get_bundle(chart_id, paid=True)
        if snapshot is None or bundle is None:
            raise DomainError("REPORT_MISSING", "Полный отчёт ещё не готов", recoverable=True)
        self.store.emit(chart_id, "pdf.started", {"report_version": bundle.schema_version})
        self.store.upsert_report(chart_id, "generating")
        try:
            report = self.pdf_renderer.render(chart_id, snapshot, bundle)
        except DomainError as exc:
            self.store.commit_report_event(chart_id, "failed", {"job_type": "pdf_v1", "code": exc.code, "recoverable": exc.recoverable}, error_code=exc.code)
            raise
        self.store.commit_report_event(
            chart_id,
            "ready",
            {"size": report["size_bytes"], "pages": report["pages"]},
            **report,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="VedicWay durable worker")
    parser.add_argument("--once", action="store_true", help="Process a single queued job")
    parser.add_argument("--drain", type=int, default=0, help="Process up to N jobs and stop")
    args = parser.parse_args()
    worker = ChartWorker(Store())
    if args.once:
        worker.process_once()
    elif args.drain:
        worker.drain(args.drain)
    else:
        while True:
            if not worker.process_once().handled:
                threading.Event().wait(0.75)


if __name__ == "__main__":
    main()
