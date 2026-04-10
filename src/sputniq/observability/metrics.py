import time
from typing import Callable, Any
from prometheus_client import Counter, Histogram, Info, generate_latest

# Define Global Metrics
AGENT_EXECUTION_COUNTER = Counter(
    "sputniq_agent_executions_total", 
    "Total number of agent workflow executions", 
    ["agent_id", "status"]
)

TOOL_INVOCATION_LATENCY = Histogram(
    "sputniq_tool_invocation_seconds", 
    "Latency of tool invocations in seconds", 
    ["tool_id"]
)

SYSTEM_INFO = Info("sputniq_build_info", "Build and version info")
SYSTEM_INFO.info({'version': '0.1.0'})

def record_tool_latency(tool_id: str):
    """Context manager decorator block to record tool latency."""
    class MetrictTimer:
        def __enter__(self):
            self.start = time.perf_counter()
            return self
            
        def __exit__(self, exc_type, *args):
            latency = time.perf_counter() - self.start
            TOOL_INVOCATION_LATENCY.labels(tool_id=tool_id).observe(latency)
            
    return MetrictTimer()

def record_agent_execution(agent_id: str, status: str = "success"):
    """Increment execution counter for a specific agent."""
    AGENT_EXECUTION_COUNTER.labels(agent_id=agent_id, status=status).inc()

def get_metrics_payload() -> bytes:
    """Return prometheus text exposition format payload."""
    return generate_latest()
