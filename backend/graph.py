"""LangGraph StateGraph — wires Searcher → (HITL steer) → Critic → Synthesizer.

The HITL pair (``ask_for_refinement`` + ``await_refinement``) pauses the
graph between Searcher and Critic so the browser can inject a steering
message. An ``InMemorySaver`` checkpointer makes resume via
``Command(resume=...)`` work end-to-end within a single process.
"""
from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from backend.agents.critic import critic_node
from backend.agents.searcher import searcher_node
from backend.agents.steer import ask_for_refinement_node, await_refinement_node
from backend.agents.synthesizer import synthesizer_node
from backend.state import ResearchState


def build_graph():
    builder = StateGraph(ResearchState)
    builder.add_node("searcher", searcher_node)
    builder.add_node("ask_for_refinement", ask_for_refinement_node)
    builder.add_node("await_refinement", await_refinement_node)
    builder.add_node("critic", critic_node)
    builder.add_node("synthesizer", synthesizer_node)

    builder.add_edge(START, "searcher")
    builder.add_edge("searcher", "ask_for_refinement")
    builder.add_edge("ask_for_refinement", "await_refinement")
    builder.add_edge("await_refinement", "critic")
    builder.add_edge("critic", "synthesizer")
    builder.add_edge("synthesizer", END)

    return builder.compile(checkpointer=InMemorySaver())


graph = build_graph()
