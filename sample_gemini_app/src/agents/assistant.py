SYSTEM_PROMPT = """You are a helpful data assistant on the Sputniq platform. 
Whenever a user asks a question, you MUST use the provided tool to fetch data before answering.
Once you receive the tool's data, summarize it cleanly for the user."""

def ApiAssistantAgent(endpoint: str, params: dict):
    # Pure Python Agent entrypoint logic (to be filled by developer)
    return f"Processed Request for API Agent with {endpoint} and {params}"
