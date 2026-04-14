import os
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

# Make sure GOOGLE_API_KEY is an alias for GEMINI_API_KEY if needed by langchain
if "GEMINI_API_KEY" in os.environ and "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

from orchestrator.graph import build_orchestrator

# Initialize FastAPI and the Orchestrator
api_app = FastAPI(title="Sputniq Gemini Sample API")
orchestrator = build_orchestrator()

class QueryRequest(BaseModel):
    query: str

@api_app.post("/api/ask")
async def ask_question(request: QueryRequest):
    if not os.environ.get("GOOGLE_API_KEY"):
        return {"error": "GOOGLE_API_KEY or GEMINI_API_KEY is not set."}

    inputs = {"messages": [HumanMessage(content=request.query)]}
    
    final_response = None
    # Stream the graph execution to get the final message content
    async for output in orchestrator.astream(inputs, stream_mode="values"):
        final_message = output["messages"][-1]
        final_response = final_message.content
        
    return {"response": final_response}

def main():
    print("=== Starting Sputniq Decoupled LangGraph Local Runner API ===")
    # Run the API server, binding to 0.0.0.0 so Docker can expose the port
    uvicorn.run(api_app, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    main()
