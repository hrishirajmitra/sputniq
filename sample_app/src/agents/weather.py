class WeatherAgent:
    def process(self, context, message):
        location = context.get("location") or message
        return f"Fetching weather guidance for: {location}"
