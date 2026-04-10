import json
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "briefings.json"


def search_briefings(query: str, limit: int = 3):
    terms = {term.lower() for term in query.split() if len(term) > 2}
    briefings = json.loads(DATA_PATH.read_text("utf-8"))
    scored = []

    for briefing in briefings:
        haystack = " ".join(
            [
                briefing["title"],
                briefing["lesson"],
                " ".join(briefing["tags"]),
                briefing["scenario"],
            ]
        ).lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, briefing))

    scored.sort(key=lambda item: (-item[0], item[1]["title"]))
    return [briefing for _, briefing in scored[:limit]]
