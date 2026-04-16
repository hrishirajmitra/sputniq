import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage
from sputniq.runtime.kafka_adapter import create_kafka_langchain_tool

SYSTEM_PROMPT = """You are a helpful data assistant on the Sputniq platform. 
Whenever a user asks a question, you MUST use the provided tool to fetch data before answering.
Once you receive the tool's data, summarize it cleanly for the user."""

def _get_llms():
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
    
    api_fetch_tool = create_kafka_langchain_tool(
        name="custom-api-fetch",
        description="Fetch data from an external API endpoint vi Kafka Event Bus.",
        req_topic=os.environ.get("TOOL_CUSTOM_API_FETCH_REQ", "sp.tools.custom-api-fetch.req"),
        res_topic=os.environ.get("TOOL_CUSTOM_API_FETCH_RES", "sp.tools.custom-api-fetch.res"),
        brokers=os.environ.get("SPUTNIQ_KAFKA_BROKERS", "localhost:9092")
    )
    tools = [api_fetch_tool]
    
    llm_forced_tool = llm.bind_tools(tools, tool_choice="custom-api-fetch")
    llm_standard = llm.bind_tools(tools)
    return llm_forced_tool, llm_standard

async def ApiAssistantAgent(state: dict):
    llm_forced_tool, _ = _get_llms()
    messages = list(state.get("messages", []))
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages
        
    print("Invoking LLM (Agent Node)...")
    response = await llm_forced_tool.ainvoke(messages)
    return {"messages": [response]}

async def ApiAssistantFinalAgent(state: dict):
    _, llm_standard = _get_llms()
    messages = list(state.get("messages", []))
    print("Invoking LLM (Final Node)...")
    response = await llm_standard.ainvoke(messages)
    return {"messages": [response]}
