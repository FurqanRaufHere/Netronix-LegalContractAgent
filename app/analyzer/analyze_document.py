# app/analyzer/analyze_document.py
import os
import json
import time
from datetime import datetime, UTC
from typing import List, Dict, Any, Optional


CHROMA_AVAILABLE = False


from app.utils.clauses import split_into_clauses
from app.llm.groq_client import call_groq_chat

LOG_DIR = os.getenv("LOG_DIR", "logs")
TRACE_FILE = os.path.join(LOG_DIR, "agent_traces.jsonl")
CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
PRECEDENT_COLLECTION_NAME = os.getenv("PRECEDENT_COLLECTION_NAME", "precedents")
DEFAULT_TOP_K = 3

# ensure logs directory exists
os.makedirs(LOG_DIR, exist_ok=True)


def _init_chroma_client(persist_directory: str = CHROMA_DIR):
    """
    Initialize Chromadb client and return (client, collection) using the new PersistentClient API.
    If the collection is absent it will be created (with a local embedding function).
    """
    try:
        import chromadb
        from chromadb.utils import embedding_functions
        client = chromadb.PersistentClient(path=persist_directory)
        try:
            coll = client.get_collection(PRECEDENT_COLLECTION_NAME)
        except Exception:
            # create a collection with a default embedding function (sentence-transformers)
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
            coll = client.create_collection(name=PRECEDENT_COLLECTION_NAME, embedding_function=ef)
        return client, coll
    except ImportError:
        return None, None



def _fallback_precedents(clause_text: str, top_k: int = DEFAULT_TOP_K) -> List[str]:
    """
    Fallback precedent lookup using simple keyword matching from data/precedents.json.
    """
    import re
    if not clause_text or not isinstance(clause_text, str):
        return []
    precedents_path = os.path.join(os.path.dirname(__file__), '../../data/precedents.json')
    try:
        with open(precedents_path, 'r', encoding='utf-8') as f:
            precedents = json.load(f)
        clause_words = set(re.findall(r'\w+', clause_text.lower()))
        scored = []
        for p in precedents:
            p_words = set(re.findall(r'\w+', p.lower()))
            score = len(clause_words & p_words)
            scored.append((score, p))
        scored.sort(reverse=True)
        return [p for score, p in scored[:top_k] if score > 0] or precedents[:top_k]
    except Exception:
        return []

def _query_precedents(collection, clause_text: str, top_k: int = DEFAULT_TOP_K) -> List[str]:
    """
    Query chroma collection for top-k similar precedent documents, or fallback if unavailable.
    """
    if CHROMA_AVAILABLE and collection is not None:
        try:
            query_res = collection.query(query_texts=[clause_text], n_results=top_k)
            docs = []
            if isinstance(query_res, dict):
                docs = query_res.get("documents", [[]])[0]
            else:
                docs = query_res.documents[0] if hasattr(query_res, "documents") else []
            docs = [d for d in docs if isinstance(d, str) and d.strip()]
            return docs
        except Exception:
            pass
    # Fallback
    return _fallback_precedents(clause_text, top_k)


def _log_trace(entry: Dict[str, Any]) -> None:
    """
    Append trace entry to JSONL trace file (one JSON object per line).
    """
    try:
        with open(TRACE_FILE, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # logging must not crash analyzer
        pass



def analyze_document_text(
    text: str,
    max_clauses: Optional[int] = 20,
    top_k_precedents: int = DEFAULT_TOP_K,
    chroma_persist_dir: Optional[str] = None,
    lll_max_tokens: int = 512,
    lll_temperature: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Analyze contract text: split into clauses, run LLM analysis, search precedents, log traces.
    Returns list of dicts: [{clause_id, clause, analysis, precedents}, ...]
    Gracefully falls back to keyword precedent search if chromadb is unavailable.
    """
    clauses = split_into_clauses(text)
    if not clauses:
        return []
    if max_clauses is not None:
        clauses = clauses[:max_clauses]
    # Setup chroma client/collection if available
    collection = None
    if CHROMA_AVAILABLE:
        try:
            client, collection = _init_chroma_client(chroma_persist_dir or CHROMA_DIR)
        except Exception:
            collection = None
    results: List[Dict[str, Any]] = []
    for clause in clauses:
        if not isinstance(clause, dict) or clause is None:
            continue
        clause_text = clause.get("text")
        if clause_text is None or not isinstance(clause_text, str):
            continue
        clause_text = clause_text.strip()
        if not clause_text:
            continue
        cid = clause.get("id")
        user_prompt = (
            f"Analyze the following contract clause and return JSON only following this schema:\n"
            '{ "risk_score": int (0-5), "reasons": [str], "redline": str }\n\n'
            f"Clause:\n\"\"\"\n{clause_text}\n\"\"\"\n"
        )
        ts = datetime.now(UTC).isoformat()
        trace_entry = {
            "ts": ts,
            "clause_id": cid,
            "clause_length": len(clause_text),
            "prompt": user_prompt[:500],
        }
        try:
            parsed = call_groq_chat(
                user_prompt=user_prompt,
                temperature=lll_temperature,
                max_tokens=lll_max_tokens,
            )
        except Exception as e:
            parsed = {"risk_score": 0, "reasons": ["llm_error"], "redline": ""}
            trace_entry["error"] = str(e)
        precedents = _query_precedents(collection, clause_text, top_k=top_k_precedents)
        analysis_obj = {
            "clause_id": cid,
            "clause": clause_text,
            "analysis": parsed,
            "precedents": precedents,
            "ts": ts,
        }
        _log_trace({**trace_entry, "response": parsed, "risk_score": parsed.get("risk_score", 0), "precedents": precedents})
        results.append(analysis_obj)
    return results
