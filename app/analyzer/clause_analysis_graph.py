"""
LangGraph workflow for clause analysis: clause extraction → LLM analysis (Langchain) → precedent search → logging.
"""
from langgraph.graph import StateGraph, END
from langchain.schema import Runnable, RunnableConfig
from typing import Dict, Any, List
from app.utils.clauses import split_into_clauses
from app.llm.groq_client import call_groq_chat_langchain
from app.analyzer.analyze_document import _init_chroma_client, _query_precedents, _log_trace
from datetime import datetime, UTC

# Define the state for the workflow
def initial_state(input_doc: Dict[str, Any]) -> Dict[str, Any]:
    text = input_doc["text"]
    max_clauses = input_doc.get("max_clauses", 10)
    clauses = split_into_clauses(text)[:max_clauses]
    return {"clauses": clauses, "results": [], "input": input_doc}

# Node: Analyze a single clause with LLM and precedents
def analyze_clause_node(state: Dict[str, Any], config: RunnableConfig = None) -> Dict[str, Any]:
    if not state["clauses"]:
        return state  # No more clauses
    clause = state["clauses"].pop(0)
    clause_text = clause.get("text", "").strip()
    cid = clause.get("id")
    user_prompt = (
        f"Analyze the following contract clause and return JSON only following this schema:\n"
        '{ "risk_score": int (0-5), "reasons": [str], "redline": str }\n\n'
        f"Clause:\n\"\"\"\n{clause_text}\n\"\"\"\n"
    )
    ts = datetime.now(UTC).isoformat()
    try:
        parsed = call_groq_chat_langchain(user_prompt)
    except Exception as e:
        parsed = {"risk_score": 0, "reasons": ["llm_error"], "redline": ""}
    # Precedents
    _, collection = _init_chroma_client()
    precedents = _query_precedents(collection, clause_text, top_k=3)
    analysis_obj = {
        "clause_id": cid,
        "clause": clause_text,
        "analysis": parsed,
        "precedents": precedents,
        "ts": ts,
    }
    # Log trace
    _log_trace({
        "ts": ts,
        "clause_id": cid,
        "prompt": user_prompt[:500],
        "response": str(parsed)[:500],
        "risk_score": parsed.get("risk_score", 0),
    })
    state["results"].append(analysis_obj)
    return state

# Node: Check if more clauses remain
def check_done_node(state: Dict[str, Any], config: RunnableConfig = None) -> str:
    return END if not state["clauses"] else "analyze"

# Build the LangGraph workflow
def build_clause_analysis_graph() -> Runnable:
    graph = StateGraph()
    graph.add_node("analyze", analyze_clause_node)
    graph.add_node("check_done", check_done_node)
    graph.set_entry_point(initial_state)
    graph.add_edge("analyze", "check_done")
    graph.add_edge("check_done", "analyze", condition=lambda state, _: state["clauses"])
    graph.add_edge("check_done", END, condition=lambda state, _: not state["clauses"])
    return graph.compile()

# Usage example (in your Streamlit or backend):
# graph = build_clause_analysis_graph()
# result_state = graph.invoke({"text": doc_text, "max_clauses": 10})
# results = result_state["results"]
