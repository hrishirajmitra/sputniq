import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import google.generativeai as genai

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Replace this with your actual API key, or map it using environment variables.
# You can update this file before zipping it.
API_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=API_KEY)

class PromptRequest(BaseModel):
    prompt: str

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
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(req.prompt)
        return {"reply": response.text}
    except Exception as e:
        return {"reply": f"Error calling Gemini: {str(e)}"}

if __name__ == "__main__":
    # Running on dynamic port provided by the sputniq orchestrator or 8120 flat
    port = int(os.environ.get("PORT", 8120))
    uvicorn.run(app, host="0.0.0.0", port=port)