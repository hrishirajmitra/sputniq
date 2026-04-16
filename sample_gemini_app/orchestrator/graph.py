import os
import sys
from typing import Annotated, TypedDict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import BaseMessage, SystemMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# The platform abstracted SDK
from sputniq.runtime.kafka_adapter import create_kafka_langchain_tool, create_kafka_agent_node

class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def build_orchestrator() -> StateGraph:
    """Builds and compiles the functional LangGraph workflow strictly over Kafka."""
    
    brokers = os.environ.get("SPUTNIQ_KAFKA_BROKERS", "localhost:9092")
    
    # 1. Platform tool bridges
    api_fetch_tool = create_kafka_langchain_tool(
        name="custom-api-fetch",
        description="Fetch data from an external API endpoint vi Kafka Event Bus.",
        req_topic=os.environ.get("TOOL_CUSTOM_API_FETCH_REQ", "sp.tools.custom-api-fetch.req"),
        res_topic=os.environ.get("TOOL_CUSTOM_API_FETCH_RES", "sp.tools.custom-api-fetch.res"),
        brokers=brokers
    )
    
    tools = [api_fetch_tool]
    tool_node = ToolNode(tools)

    # 2. Platform agent bridges
    agent_node = create_kafka_agent_node(
        agent_id="api-assistant",
        req_topic=os.environ.get("AGENT_API_ASSISTANT_REQ", "sp.agents.api-assistant.req"),
        res_topic=os.environ.get("AGENT_API_ASSISTANT_RES", "sp.agents.api-assistant.res"),
        brokers=brokers
    )

    final_response_node = create_kafka_agent_node(
        agent_id="api-assistant-final",
        req_topic=os.environ.get("AGENT_API_ASSISTANT_FINAL_REQ", "sp.agents.api-assistant-final.req"),
        res_topic=os.environ.get("AGENT_API_ASSISTANT_FINAL_RES", "sp.agents.api-assistant-final.res"),
        brokers=brokers
    )

    def should_continue(state: GraphState):
        messages = state["messages"]
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    # 3. LangGraph Orchestration definition
    builder = StateGraph(GraphState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.add_node("final", final_response_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "final")
    builder.add_edge("final", END)

    return builder.compile()
