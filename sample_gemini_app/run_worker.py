import asyncio
import os

# Sputniq platform abstracts away Kafka concepts
from sputniq.runtime.kafka_adapter import run_tool_worker

# The pure python developer code
from src.tools.api_fetch import fetch_api_data

if __name__ == "__main__":
    brokers = os.environ.get("SPUTNIQ_KAFKA_BROKERS", "localhost:9092")
    req_topic = os.environ.get("TOOL_CUSTOM_API_FETCH_REQ", "sp.tools.custom-api-fetch.req")
    res_topic = os.environ.get("TOOL_CUSTOM_API_FETCH_RES", "sp.tools.custom-api-fetch.res")
    
    # Let the platform manage binding the developer function to the message bus via daemon loop
    asyncio.run(run_tool_worker(
        func=fetch_api_data,
        tool_id="custom-api-fetch",
        req_topic=req_topic,
        res_topic=res_topic,
        brokers=brokers
    ))
