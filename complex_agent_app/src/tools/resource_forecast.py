def forecast_resources(goal: str, phases=None):
    phases = phases or []
    goal_lower = goal.lower()

    roles = ["Operator", "Technical Lead", "Project Manager"]
    if any(keyword in goal_lower for keyword in ["launch", "release", "deploy", "ship"]):
        roles.append("Release Manager")
    if any(keyword in goal_lower for keyword in ["data", "migration", "import", "sync"]):
        roles.append("Data Lead")
    if any(keyword in goal_lower for keyword in ["support", "customer", "ops"]):
        roles.append("Support Lead")

    checkpoints = [
        "Mission intake approved",
        "Execution design reviewed",
        "Risk readout shared",
    ]
    if phases:
        checkpoints.append(f"{len(phases)} phases staffed")

    return {
        "timeline_days": max(5, len(phases) * 3 + len(roles) - 1),
        "roles": roles,
        "checkpoints": checkpoints,
    }
