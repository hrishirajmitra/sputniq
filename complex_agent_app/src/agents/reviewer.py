class ReviewAgent:
    async def run(self, ctx):
        request = ctx.input["message"]
        risks = await ctx.tool("risk-matrix", goal=request)
        briefings = await ctx.tool("briefing-search", query=request)

        headline = risks[0]["risk"] if risks else "Execution drift"
        lesson = (
            briefings[0]["lesson"]
            if briefings
            else "No close briefing match, so validate assumptions early."
        )

        ctx.emit(
            "review_complete",
            {
                "primary_risk": headline,
                "briefing_hits": len(briefings),
            },
        )

        return "\n".join(
            [
                "Review Agent",
                f"Primary challenge: {headline}",
                f"Best historical lesson: {lesson}",
                "Recommended next action: tighten ownership and add a checkpoint before external launch.",
            ]
        )
