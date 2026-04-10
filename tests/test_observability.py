import pytest
from unittest.mock import patch, MagicMock

from sputniq.observability.tracing import setup_tracing, get_tracer
from sputniq.observability.metrics import record_tool_latency, record_agent_execution, get_metrics_payload

def test_tracing_setup():
    with patch("sputniq.observability.tracing.trace.set_tracer_provider") as mock_set_provider, \
         patch("sputniq.observability.tracing.OTLPSpanExporter") as mock_exporter, \
         patch("sputniq.observability.tracing.BatchSpanProcessor") as mock_processor, \
         patch("sputniq.observability.tracing.trace.get_tracer") as mock_get_tracer:
         
         tracer = setup_tracing("my-service", "http://jaeger:4317")
         
         mock_exporter.assert_called_once_with(endpoint="http://jaeger:4317", insecure=True)
         mock_set_provider.assert_called_once()
         mock_get_tracer.assert_called_once_with("my-service")

def test_metrics_agent_execution():
    record_agent_execution("agent-x", "success")
    record_agent_execution("agent-x", "failed")
    
    payload = get_metrics_payload().decode("utf-8")
    
    assert 'sputniq_agent_executions_total{agent_id="agent-x",status="success"} 1.0' in payload
    assert 'sputniq_agent_executions_total{agent_id="agent-x",status="failed"} 1.0' in payload

def test_metrics_tool_latency():
    import time
    with record_tool_latency("tool-123"):
        time.sleep(0.01) # fake operation
        
    payload = get_metrics_payload().decode("utf-8")
    assert 'sputniq_tool_invocation_seconds_count{tool_id="tool-123"} 1.0' in payload