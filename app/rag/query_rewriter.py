from app.llm.planner.turn_planner import TurnPlan, TurnPlanner

SearchQuery = TurnPlan
QueryRewriter = TurnPlanner

__all__ = ["QueryRewriter", "SearchQuery", "TurnPlan", "TurnPlanner"]
