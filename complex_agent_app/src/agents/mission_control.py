def _flatten_task_names(plan: dict) -> list[str]:
    tasks: list[str] = []
    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            tasks.append(task["name"])
    return tasks


def _previous_focus(history: list[dict]) -> str | None:
    user_messages = [
        item.get("content", "").strip()
        for item in history
        if item.get("role") == "user" and item.get("content")
    ]
    if not user_messages:
        return None
    return user_messages[-1][:96]


class MissionControlAgent:
    async def run(self, ctx):
        request = ctx.input["message"]
        history = ctx.input.get("history", [])

        plan = await ctx.tool("task-graph", goal=request)
        task_names = _flatten_task_names(plan)
        briefings = await ctx.tool("briefing-search", query=request)
        risks = await ctx.tool("risk-matrix", goal=request, tasks=task_names)
        forecast = await ctx.tool("resource-forecast", goal=request, phases=plan["phases"])

        ctx.emit(
            "mission_brief_ready",
            {
                "phase_count": len(plan["phases"]),
                "risk_count": len(risks),
                "briefing_hits": len(briefings),
            },
        )

        lines = [
            "Mission Control Brief",
            f"Request: {request}",
        ]

        previous_focus = _previous_focus(history)
        if previous_focus:
            lines.append(f"Prior focus from this chat: {previous_focus}")

        lines.extend(
            [
                "",
                "Recommended execution lanes:",
            ]
        )

        for phase in plan["phases"]:
            lines.append(f"- {phase['name']}: {phase['summary']}")
            for task in phase["tasks"]:
                lines.append(
                    f"  - {task['name']} ({task['owner']}, {task['duration_days']}d)"
                )

        lines.extend(
            [
                "",
                "Operational risks:",
            ]
        )
        for risk in risks:
            lines.append(
                f"- {risk['risk']} [{risk['severity']}] - {risk['mitigation']}"
            )

        lines.extend(
            [
                "",
                "Resource forecast:",
                f"- Timeline: {forecast['timeline_days']} working days",
                f"- Core roles: {', '.join(forecast['roles'])}",
                f"- Checkpoints: {', '.join(forecast['checkpoints'])}",
            ]
        )

        if briefings:
            lines.extend(["", "Relevant past briefings:"])
            for briefing in briefings:
                lines.append(
                    f"- {briefing['title']}: {briefing['lesson']} ({', '.join(briefing['tags'])})"
                )
        else:
            lines.extend(["", "Relevant past briefings: none matched this request closely."])

        return "\n".join(lines)
