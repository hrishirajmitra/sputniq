import asyncio
import os

# Sputniq platform abstracts away Kafka concepts
from sputniq.runtime.kafka_adapter import run_tool_worker, run_agent_worker

# The pure python developer code
from src.tools.api_fetch import fetch_api_data
from src.agents.assistant import ApiAssistantAgent, ApiAssistantFinalAgent

async def main():
    brokers = os.environ.get("SPUTNIQ_KAFKA_BROKERS", "localhost:9092")
    
    # Tool specifics
    tool_req_topic = os.environ.get("TOOL_CUSTOM_API_FETCH_REQ", "sp.tools.custom-api-fetch.req")
    tool_res_topic = os.environ.get("TOOL_CUSTOM_API_FETCH_RES", "sp.tools.custom-api-fetch.res")
    
    # Agent specifics
    agent_req_topic = os.environ.get("AGENT_API_ASSISTANT_REQ", "sp.agents.api-assistant.req")
    agent_res_topic = os.environ.get("AGENT_API_ASSISTANT_RES", "sp.agents.api-assistant.res")

    final_agent_req_topic = os.environ.get("AGENT_API_ASSISTANT_FINAL_REQ", "sp.agents.api-assistant-final.req")
    final_agent_res_topic = os.environ.get("AGENT_API_ASSISTANT_FINAL_RES", "sp.agents.api-assistant-final.res")
    
    # Let the platform manage binding the developer function to the message bus via daemon loop
    tool_task = run_tool_worker(
        func=fetch_api_data,
        tool_id="custom-api-fetch",
        req_topic=tool_req_topic,
        res_topic=tool_res_topic,
        brokers=brokers
    )
    
    agent_task = run_agent_worker(
        agent_func=ApiAssistantAgent,
        agent_id="api-assistant",
        req_topic=agent_req_topic,
        res_topic=agent_res_topic,
        brokers=brokers
    )
    
    final_agent_task = run_agent_worker(
        agent_func=ApiAssistantFinalAgent,
        agent_id="api-assistant-final",
        req_topic=final_agent_req_topic,
        res_topic=final_agent_res_topic,
        brokers=brokers
    )

    await asyncio.gather(tool_task, agent_task, final_agent_task)

if __name__ == "__main__":
    asyncio.run(main())
