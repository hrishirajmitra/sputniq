from typing import Dict, Any

async def get_weather(location: str) -> Dict[str, Any]:
    """
    Mock weather tool that returns a standardized dictionary response.
    In a real implementation, this would call an external API.
    """
    location_lower = location.lower()
    
    if "tokyo" in location_lower:
        return {"temperature": 18.0, "condition": "Cloudy"}
    elif "london" in location_lower:
        return {"temperature": 14.5, "condition": "Rainy"}
    elif "seattle" in location_lower:
        return {"temperature": 16.0, "condition": "Overcast"}
    else:
        # Default weather for unknown locations
        return {"temperature": 22.0, "condition": "Sunny"}
