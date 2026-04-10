import logging
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

def setup_tracing(service_name: str, endpoint: str = "http://localhost:4317"):
    """
    Configure OpenTelemetry tracer to export to an OTLP endpoint (e.g. Jaeger).
    """
    logger.info(f"Setting up tracing for {service_name} exporting to {endpoint}")
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    
    # Configure OTLP exporter
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    processor = BatchSpanProcessor(exporter)
    provider.add_span_processor(processor)
    
    # Set global provider
    trace.set_tracer_provider(provider)
    return trace.get_tracer(service_name)
    
def get_tracer(module_name: str):
    """Retrieve a configured tracer for a specific module."""
    return trace.get_tracer(module_name)
