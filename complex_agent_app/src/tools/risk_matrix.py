def generate_risk_matrix(goal: str, tasks=None):
    goal_lower = goal.lower()
    tasks = tasks or []
    risks = [
        {
            "risk": "Ownership blur between parallel tracks",
            "severity": "high",
            "mitigation": "Assign a single accountable owner to every phase before execution starts.",
        },
        {
            "risk": "Late discovery of dependency changes",
            "severity": "medium",
            "mitigation": "Create a checkpoint after the first planning pass and review blocked tasks explicitly.",
        },
    ]

    if any(keyword in goal_lower for keyword in ["launch", "release", "deploy", "ship"]):
        risks.append(
            {
                "risk": "Launch-day rollback path is under-specified",
                "severity": "high",
                "mitigation": "Document rollback triggers and rehearse who approves rollback before launch day.",
            }
        )

    if any(keyword in goal_lower for keyword in ["data", "migration", "import", "sync"]):
        risks.append(
            {
                "risk": "Data drift between source and destination systems",
                "severity": "high",
                "mitigation": "Run sampled reconciliation and block release until drift stays below tolerance.",
            }
        )

    if len(tasks) > 6:
        risks.append(
            {
                "risk": "Execution surface is too wide for a single review loop",
                "severity": "medium",
                "mitigation": "Split the work into milestones with explicit sign-off after each major lane.",
            }
        )

    return risks
