from typing import Any
from sputniq.sdk.decorators import agent
from sputniq.sdk.context import AgentContext

@agent(id="weather-agent")
class WeatherAgent:
    async def run(self, ctx: AgentContext) -> str:
        # Access the user's input/query
        user_input = ctx.input.get("query", "What is the weather?") if isinstance(ctx.input, dict) else str(ctx.input)

        # In a real scenario, the agent would use an LLM or logic to extract the location from `user_input`.
        # For simplicity, we'll try a basic check or just default to a city.
        location = "Seattle, WA"
        if "tokyo" in user_input.lower():
            location = "Tokyo, Japan"
        elif "london" in user_input.lower():
            location = "London, UK"
            
        # Use a tool configured in config.json
        weather_data = await ctx.tool("get-weather", location=location)
        
        # Prepare messages for the LLM model configured in config.json
        messages = [
            {"role": "system", "content": "You are a helpful weather assistant. Summarize the weather data given."},
            {"role": "user", "content": f"The weather in {location} is {weather_data['temperature']}°C and {weather_data['condition']}."}
        ]
        
        # Invoke the model named 'gemini-2.5-flash' (must match config.json models list)
        response = await ctx.model("gemini-2.5-flash", messages=messages)
        
        # Emit an event for observability
        ctx.emit("weather_reported", {"location": location, "report": response})
        
        return response
