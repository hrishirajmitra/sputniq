import os
import sys
from typing import Annotated, TypedDict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

# The developer's pure Python resources
from src.agents.assistant import SYSTEM_PROMPT

# The platform abstracted SDK
from sputniq.runtime.kafka_adapter import create_kafka_langchain_tool

class GraphState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

def build_orchestrator() -> StateGraph:
    """Builds and compiles the functional LangGraph workflow."""
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    
    # 1. The platform automatically bridges the tool to Kafka without the dev doing anything
    api_fetch_tool = create_kafka_langchain_tool(
        name="custom-api-fetch",
        description="Fetch data from an external API endpoint vi Kafka Event Bus.",
        req_topic=os.environ.get("TOOL_CUSTOM_API_FETCH_REQ", "sp.tools.custom-api-fetch.req"),
        res_topic=os.environ.get("TOOL_CUSTOM_API_FETCH_RES", "sp.tools.custom-api-fetch.res"),
        brokers=os.environ.get("SPUTNIQ_KAFKA_BROKERS", "localhost:9092")
    )
    
    tools = [api_fetch_tool]
    
    # 2. Setup LLM & Tools
    llm_forced_tool = llm.bind_tools(tools, tool_choice="custom-api-fetch")
    llm_standard = llm.bind_tools(tools)

    def agent_node(state: GraphState):
        messages = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
            
        print("Invoking LLM...")
        response = llm_forced_tool.invoke(messages)
        return {"messages": [response]}
        
    def final_response_node(state: GraphState):
        response = llm_standard.invoke(state["messages"])
        return {"messages": [response]}

    tool_node = ToolNode(tools)

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
