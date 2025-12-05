# app/utils/clauses.py
import re
from typing import List, Dict, Any, Tuple

DEFAULT_MIN_LEN = 40        # minimum clause length to keep
DEFAULT_MAX_LEN = 2000      # maximum clause length before attempting to chunk

_header_patterns = [
    # captures headings like "Section 1.", "Section 1:", "Clause 2.", "CLAUSE 2 -", "1. DEFINITIONS"
    r'(?m)^(Section|Clause)\s+\d+[\.\: -]?',            # Section 1. / Clause 2:
    r'(?m)^[A-Z][A-Z\s]{4,}\n',                         # ALL CAPS heading line (>=5 chars)
    r'(?m)^\d+\.\s+[A-Z][A-Za-z\s]{3,}\n',              # "1. Definitions" (heading line, capitalized)
    r'(?m)^[0-9]+\.[0-9]+\s+',                          # 1.1 Subsection marker
]

# Combine into one regex for splitting while keeping headings
_SPLIT_RE = re.compile(r'(' + r'|'.join(p.strip('(?m)') for p in _header_patterns) + r')', flags=re.MULTILINE)


def _normalize_whitespace(s: str) -> str:
    # collapse multiple newlines into double newline, strip surrounding whitespace
    s = re.sub(r'\r\n?', '\n', s)
    s = re.sub(r'\n\s*\n\s*\n+', '\n\n', s)  # no more than double newline
    s = re.sub(r'[ \t]{2,}', ' ', s)
    return s.strip()


def _chunk_long_clause(text: str, max_len: int) -> List[str]:
    """
    If a clause is very long (> max_len), chunk it into roughly sentence-boundary pieces.
    """
    if text is None or not isinstance(text, str) or len(text) <= max_len:
        return [text] if text else []
    sentences = re.split(r'(?<=[\.\?\!])\s+', text)
    chunks = []
    current = []
    cur_len = 0
    for s in sentences:
        if s is None:
            continue
        if cur_len + len(s) <= max_len:
            current.append(s)
            cur_len += len(s)
        else:
            if current:
                chunks.append(" ".join(current).strip())
            # if single sentence is longer than max_len, force-split
            if len(s) > max_len:
                # split the long sentence every max_len chars
                for i in range(0, len(s), max_len):
                    part = s[i:i+max_len].strip()
                    if part:
                        chunks.append(part)
                current = []
                cur_len = 0
            else:
                current = [s]
                cur_len = len(s)
    if current:
        chunks.append(" ".join(current).strip())
    return chunks


def split_into_clauses(text: str,
                       min_len: int = DEFAULT_MIN_LEN,
                       max_len: int = DEFAULT_MAX_LEN,
                       debug: bool = False) -> List[Dict[str, Any]]:
    """
    Split `text` into a list of clause objects:
      [{"id": 0, "text": "...", "source_heading": "<heading or None>", "too_short": False}, ...]

    Strategy:
      1. Normalize whitespace.
      2. Try header-aware splitting using common heading patterns.
      3. If header split yields only one big block, fallback to paragraph split (double newline).
      4. Filter out fragments shorter than `min_len`.
      5. If a block exceeds `max_len`, chunk it intelligently by sentence boundaries.

    Parameters:
      - min_len: minimum characters to accept as a clause
      - max_len: preferred maximum characters per clause (will chunk larger blocks)
      - debug: if True, include debug markers (start/end indices)

    Returns list of dicts sorted in original order.
    """
    if not isinstance(text, str):
        raise ValueError("text must be a string")

    text = _normalize_whitespace(text)
    if not text:
        return []

    # Try header-aware split
    # We'll find headings and split at their positions while keeping headings attached to following text.
    parts: List[Tuple[str, int, int]] = []  # (text, start_idx, end_idx)

    # find all heading matches
    matches = list(_SPLIT_RE.finditer(text))
    if matches:
        # build segments from headings positions
        last_idx = 0
        for m in matches:
            start = m.start()
            # previous chunk (if any)
            if start > last_idx:
                chunk = text[last_idx:start].strip()
                if chunk:
                    parts.append((chunk, last_idx, start))
            # include the heading and following content; find the end by next match or end of text
            last_idx = start
        # add final tail
        final_chunk = text[last_idx:].strip()
        if final_chunk:
            parts.append((final_chunk, last_idx, len(text)))
    else:
        # fallback: paragraph split (double newline)
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        idx = 0
        parts = []
        for p in paragraphs:
            parts.append((p, idx, idx + len(p)))
            idx += len(p) + 2  # approximate position for debug

    # If header-splitting resulted in single huge block, fallback to paragraph split
    if len(parts) == 1:
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        if len(paragraphs) > 1:
            parts = []
            idx = 0
            for p in paragraphs:
                parts.append((p, idx, idx + len(p)))
                idx += len(p) + 2

    # Now process each part: filter short, chunk long, attach metadata
    clauses: List[Dict[str, Any]] = []
    cid = 0
    for part_text, start_idx, end_idx in parts:
        # if too long -> chunk
        chunks = _chunk_long_clause(part_text, max_len)
        for c in chunks:
            c = c.strip()
            if c is None:
                continue
            too_short = len(c) < min_len
            if too_short:
                # try to merge with previous clause if exists
                if clauses:
                    # append this small fragment to previous clause to avoid tiny fragments
                    clauses[-1]['text'] = clauses[-1]['text'] + "\n\n" + c
                    clauses[-1]['too_short'] = len(clauses[-1]['text']) < min_len
                    continue
                # else keep it (first fragment), but mark too_short
            entry: Dict[str, Any] = {
                "id": cid,
                "text": c,
                "length": len(c),
                "too_short": too_short,
            }
            if debug:
                entry["start_idx"] = start_idx
                entry["end_idx"] = end_idx
            clauses.append(entry)
            cid += 1

    # Final pass: remove any fragments still below min_len if there are other clauses (avoid returning tiny noise)
    if len(clauses) > 1:
        clauses = [c for c in clauses if not (c['too_short'] and c['length'] < min_len)]

    return clauses
