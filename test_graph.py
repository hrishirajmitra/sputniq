import os
import requests

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing import Annotated, TypedDict

API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyCDNW59Pk8wnPx_Oq2cs4hBXoSx3iXfExw")

class State(TypedDict):
    messages: Annotated[list, add_messages]

@tool
def web_search(query: str) -> str:
    """Searches the web for information using the external search service."""
    # Let's hit the endpoint to see what happens
    try:
        response = requests.post("http://localhost:37635/api/tool", json={"query": query}, timeout=5)
        response.raise_for_status()
        return str(response.json().get("result", "No result returned."))
    except Exception as e:
        return f"Error calling web search tool: {str(e)}"

tools_list = [web_search]
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", api_key=API_KEY)
llm_with_tools = llm.bind_tools(tools_list)

def chatbot(state: State):
    print("Chatbot running")
    msg = llm_with_tools.invoke(state["messages"])
    print(f"Chatbot output: {msg}")
    return {"messages": [msg]}

graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)
tool_node = ToolNode(tools=tools_list)
graph_builder.add_node("tools", tool_node)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges("chatbot", tools_condition)
graph_builder.add_edge("tools", "chatbot")
graph = graph_builder.compile()

sys_msg = SystemMessage(content="You are a helpful research agent. You MUST use the `web_search` tool to look up information. After receiving the search results, directly provide the answer based on what the tool returned without asking for more context.")
final_state = graph.invoke({"messages": [sys_msg, HumanMessage(content="what did archit do")]})
print("\n--- FINAL STATE ---")
for m in final_state["messages"]:
    print(f"{type(m).__name__}: {m.content}")

