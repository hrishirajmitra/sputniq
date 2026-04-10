import os
import uvicorn
import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing import Annotated, TypedDict

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Replace this with your actual API key, or map it using environment variables.
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyCCNNQMQ4GRb3hyh-HfzIaen56smMlAbYM")

class PromptRequest(BaseModel):
    prompt: str

# -------------------------------------------------------------
# LangGraph Setup
# -------------------------------------------------------------

class State(TypedDict):
    messages: Annotated[list, add_messages]

@tool
def web_search(query: str) -> str:
    """Searches the web for information using the external search service."""
    # Use dynamic orchestrator URL, fallback to localhost
    tool_url = os.environ.get("WEB_SEARCH_SERVICE_URL", "http://localhost:8005/api/tool")
    try:
        response = requests.post(tool_url, json={"query": query}, timeout=10)
        response.raise_for_status()
        return str(response.json().get("result", "No result returned."))
    except requests.exceptions.ConnectionError:
        # Try docker DNS as fallback if localhost fails, or vice versa
        try:
            fallback_url = "http://web-search:8005/api/tool"
            response = requests.post(fallback_url, json={"query": query}, timeout=10)
            response.raise_for_status()
            return str(response.json().get("result", "No result returned."))
        except Exception as fallback_e:
            return f"Error calling web search tool (failed both localhost and web-search): {str(fallback_e)}"
    except Exception as e:
        return f"Error calling web search tool: {str(e)}"

tools_list = [web_search]
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", api_key=API_KEY)
llm_with_tools = llm.bind_tools(tools_list)

def chatbot(state: State):
    return {"messages": [llm_with_tools.invoke(state["messages"])]}

graph_builder = StateGraph(State)
graph_builder.add_node("chatbot", chatbot)

tool_node = ToolNode(tools=tools_list)
graph_builder.add_node("tools", tool_node)

graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges("chatbot", tools_condition)
graph_builder.add_edge("tools", "chatbot")

graph = graph_builder.compile()

# -------------------------------------------------------------
# API Routes
# -------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    return """
    <html>
        <head><title>Research Agent UI</title></head>
        <body style="font-family: sans-serif; background: #0f172a; color: white; padding: 2rem; max-width: 600px; margin: auto;">
            <h2>🤖 Research Agent Chat</h2>
            <div id="chat" style="height: 300px; overflow-y: auto; background: #1e293b; padding: 1rem; border-radius: 8px; margin-bottom: 1rem; white-space: pre-wrap;"></div>
            <input type="text" id="prompt" style="width: 70%; padding: 0.5rem; border-radius: 4px; border: 1px solid #475569; background: #334155; color: white;" placeholder="Ask me something...">
            <button onclick="send()" style="width: 25%; padding: 0.5rem; background: #0ea5e9; color: white; border: none; border-radius: 4px; cursor: pointer;">Send</button>
            <script>
                async function send() {
                    const inp = document.getElementById('prompt');
                    const chat = document.getElementById('chat');
                    const text = inp.value;
                    if(!text) return;
                    chat.innerHTML += `<br><b>You:</b> ${text}\\n`;
                    inp.value = '';
                    try {
                        const res = await fetch('/api/research', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({prompt: text})
                        });
                        const data = await res.json();
                        chat.innerHTML += `<br><b>Agent:</b> ${data.reply}\\n`;
                    } catch(e) {
                        chat.innerHTML += `<br><b style="color:red">Error:</b> ${e}\\n`;
                    }
                    chat.scrollTop = chat.scrollHeight;
                }
            </script>
        </body>
    </html>
    """

@app.post("/api/research")
def research(req: PromptRequest):
    try:
        sys_msg = SystemMessage(content="You are a helpful research agent. You MUST use the `web_search` tool to look up information. After receiving the search results, directly provide the answer based on what the tool returned without asking for more context.")
        initial_state = {"messages": [sys_msg, HumanMessage(content=req.prompt)]}
        final_state = graph.invoke(initial_state)
        # Final message content is the agent's response
        last_message = final_state["messages"][-1]
        
        reply_content = last_message.content
        if isinstance(reply_content, list):
            # If content is a list of blocks, extract text or stringify
            reply_content = " ".join(block.get("text", str(block)) if isinstance(block, dict) else str(block) for block in reply_content)
        elif not isinstance(reply_content, str):
            reply_content = str(reply_content)
            
        return {"reply": reply_content}
    except Exception as e:
        return {"reply": f"Error during agent execution: {str(e)}"}

if __name__ == "__main__":
    # Running on dynamic port provided by the sputniq orchestrator or 8120 flat
    port = int(os.environ.get("PORT", 8120))
    uvicorn.run(app, host="0.0.0.0", port=port)