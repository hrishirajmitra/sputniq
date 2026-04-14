"""Weather Agent — sample app demonstrating the Sputniq SDK.

Uses the @agent decorator and AgentContext to interact with tools and models.
"""

from sputniq.sdk.decorators import agent
from sputniq.sdk.context import AgentContext


@agent(id="weather-agent")
class WeatherAgent:
    """Answers questions about the weather using tools and models."""

    async def run(self, ctx: AgentContext) -> str:
        """Main agent loop.

        1. Extract the location from input
        2. Call the get-weather tool
        3. Use the model to generate a natural-language response
        """
        location = ctx.input if isinstance(ctx.input, str) else "London"
        ctx.logger.info("WeatherAgent invoked for location: %s", location)

        # Step 1: Invoke the weather tool
        ctx.emit("tool_call_start", {"tool": "get-weather", "location": location})
        weather_data = await ctx.tool("get-weather", location=location)
        ctx.emit("tool_call_end", {"tool": "get-weather", "result": weather_data})

        # Step 2: Synthesize a user-facing response via the LLM
        response = await ctx.model(
            "gpt-mock",
            messages=[
                {"role": "system", "content": "You are a helpful weather assistant."},
                {"role": "user", "content": f"Summarize this weather data: {weather_data}"},
            ],
        )

        ctx.emit("agent_response", {"response": response})
        return response

    def process(self, context, message):
        """Legacy synchronous interface for backward compatibility."""
        location = context.get("location") if isinstance(context, dict) else message
        return f"Fetching weather guidance for: {location}"
