def _phase(name: str, summary: str, tasks: list[tuple[str, str, int]]):
    return {
        "name": name,
        "summary": summary,
        "tasks": [
            {
                "name": task_name,
                "owner": owner,
                "duration_days": duration_days,
            }
            for task_name, owner, duration_days in tasks
        ],
    }


def create_task_graph(goal: str):
    goal_lower = goal.lower()
    phases = [
        _phase(
            "Signal Intake",
            "Capture the ask, constraints, and decision deadline.",
            [
                ("Confirm objective and success metric", "Operator", 1),
                ("List blockers and assumptions", "Operator", 1),
            ],
        ),
        _phase(
            "Execution Design",
            "Turn the objective into concrete lanes of work.",
            [
                ("Break work into parallel tracks", "Planner", 2),
                ("Assign clear owners per track", "Lead", 1),
            ],
        ),
    ]

    if any(keyword in goal_lower for keyword in ["launch", "release", "deploy", "ship"]):
        phases.append(
            _phase(
                "Launch Readiness",
                "Harden rollout, communications, and rollback guardrails.",
                [
                    ("Run launch checklist", "Release Manager", 2),
                    ("Prepare rollback and support plan", "SRE", 1),
                ],
            )
        )

    if any(keyword in goal_lower for keyword in ["data", "migration", "import", "sync"]):
        phases.append(
            _phase(
                "Data Controls",
                "Validate migration quality before broad exposure.",
                [
                    ("Sample and reconcile migrated records", "Data Lead", 2),
                    ("Define fallback handling for bad rows", "Backend Engineer", 1),
                ],
            )
        )

    if any(keyword in goal_lower for keyword in ["customer", "support", "ops"]):
        phases.append(
            _phase(
                "Field Enablement",
                "Prepare the people handling live issues on day one.",
                [
                    ("Draft support playbook", "Support Lead", 1),
                    ("Brief escalation owners", "Operations", 1),
                ],
            )
        )

    return {
        "goal": goal,
        "phases": phases,
        "critical_path": [phase["name"] for phase in phases[:3]],
    }
