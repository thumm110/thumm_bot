def build_research_brief(signal):
    return {
        "ticker": signal.get("ticker"),
        "title": signal.get("title"),
        "decision": signal.get("decision"),
        "score": signal.get("score"),
        "status": "pending_agent_review",
    }
