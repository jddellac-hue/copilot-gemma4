"""OpenTelemetry instrumentation for the agent harness.

Each agent run is a root span. Each step is a child span. Each model call
and tool call are leaves. Metrics and structured logs complement traces.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)


@dataclass
class ObservabilityConfig:
    enabled: bool = True
    service_name: str = "agent-harness"
    otlp_endpoint: str | None = None  # e.g. "http://localhost:4317"


def setup_observability(config: ObservabilityConfig) -> Observability:
    """Initialise tracing and metrics. Idempotent."""
    if not config.enabled:
        return Observability(enabled=False)

    resource = Resource.create({"service.name": config.service_name})
    provider = TracerProvider(resource=resource)
    if config.otlp_endpoint:
        exporter = OTLPSpanExporter(endpoint=config.otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(_NullMetricExporter())]
        if not config.otlp_endpoint
        else [],
    )
    metrics.set_meter_provider(meter_provider)

    return Observability(enabled=True)


class _NullMetricExporter:
    """Placeholder when no OTLP endpoint is configured."""

    def export(self, *args: Any, **kwargs: Any) -> int:
        return 0

    def shutdown(self, *args: Any, **kwargs: Any) -> None:
        return None

    def force_flush(self, *args: Any, **kwargs: Any) -> bool:
        return True


@dataclass
class Observability:
    enabled: bool = True

    def __post_init__(self) -> None:
        self._tracer = trace.get_tracer("agent.harness")
        self._meter = metrics.get_meter("agent.harness")
        self._step_counter = self._meter.create_counter(
            "agent_steps_total", description="Number of agent loop steps"
        )
        self._tool_counter = self._meter.create_counter(
            "agent_tool_calls_total", description="Number of tool calls"
        )
        self._token_counter = self._meter.create_counter(
            "agent_model_tokens_total", description="Tokens consumed by the model"
        )
        self._permission_denied = self._meter.create_counter(
            "agent_permission_denied_total",
            description="Tool calls denied by the permission policy",
        )

    @contextlib.contextmanager
    def session(self, session_id: str) -> Iterator[Any]:
        with self._tracer.start_as_current_span("agent.session") as span:
            span.set_attribute("session.id", session_id)
            yield span

    @contextlib.contextmanager
    def step(self, step_index: int) -> Iterator[Any]:
        with self._tracer.start_as_current_span(f"agent.step.{step_index}") as span:
            span.set_attribute("step.index", step_index)
            self._step_counter.add(1)
            yield span

    @contextlib.contextmanager
    def model_call(self, model_name: str) -> Iterator[Any]:
        with self._tracer.start_as_current_span("model.call") as span:
            span.set_attribute("model.name", model_name)
            yield span

    @contextlib.contextmanager
    def tool_call(self, tool_name: str, risk: str) -> Iterator[Any]:
        with self._tracer.start_as_current_span(f"tool.{tool_name}") as span:
            span.set_attribute("tool.name", tool_name)
            span.set_attribute("tool.risk", risk)
            self._tool_counter.add(1, {"tool": tool_name})
            yield span

    def record_tokens(self, model: str, in_tokens: int, out_tokens: int) -> None:
        self._token_counter.add(in_tokens, {"model": model, "direction": "in"})
        self._token_counter.add(out_tokens, {"model": model, "direction": "out"})

    def record_denied(self, tool_name: str) -> None:
        self._permission_denied.add(1, {"tool": tool_name})
