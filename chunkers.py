"""Chunker registry for P04: name -> function(section, max_words, overlap) -> chunks."""

import re
from collections.abc import Callable

from rag_contracts import DocumentChunk, ParsedSection

Chunker = Callable[[ParsedSection, int, int], list[DocumentChunk]]


def _windows(words: list[str], max_words: int, overlap: int) -> list[list[str]]:
    step = max(1, max_words - overlap)
    if not words:
        return []
    return [words[s : s + max_words] for s in range(0, max(1, len(words) - overlap), step)]


def _make_chunk(sec: ParsedSection, chunk_id: str, words: list[str]) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        parent_section_id=sec.section_id,
        doc_id=sec.doc_id,
        text=" ".join(words),
        token_count=len(words),
        header_hierarchy=sec.header_path,
        parent_markdown=f"### {' > '.join(sec.header_path)}\n{sec.body}",
    )


def chunk_sliding_window(sec: ParsedSection, max_words: int, overlap: int) -> list[DocumentChunk]:
    wins = _windows(sec.body.split(), max_words, overlap)
    return [_make_chunk(sec, f"{sec.section_id}_chk_{i}", w) for i, w in enumerate(wins)]


def chunk_recursive(sec: ParsedSection, max_words: int, overlap: int) -> list[DocumentChunk]:
    """Paragraph -> sentence -> word-window fallback. `overlap` is ignored."""
    pieces: list[list[str]] = []
    for para in (p.strip() for p in sec.body.split("\n\n")):
        if not para:
            continue
        if len(para.split()) <= max_words:
            pieces.append(para.split())
            continue
        for sent in re.split(r"(?<=[.!?])\s+", para):
            words = sent.split()
            if len(words) <= max_words:
                if words:
                    pieces.append(words)
            else:
                pieces.extend(_windows(words, max_words, 0))
    return [_make_chunk(sec, f"{sec.section_id}_rec_{n}", w) for n, w in enumerate(pieces)]


CHUNKERS: dict[str, Chunker] = {
    "sliding_window": chunk_sliding_window,
    "recursive": chunk_recursive,
}


def resolve_chunker(name: str) -> Chunker:
    try:
        return CHUNKERS[name]
    except KeyError:
        raise KeyError(f"Unknown chunker '{name}'. Known: {', '.join(sorted(CHUNKERS))}") from None
