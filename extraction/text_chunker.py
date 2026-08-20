"""Vietnamese Clinical Text Chunker with Heading Heuristic and Sentence Overlap."""

import re
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TextChunk:
    chunk_id: int
    text: str
    start_char: int
    end_char: int
    section_title: str


_HEADING_REGEX = re.compile(
    r"^(?:#{1,6}\s+(.+)|(?:\d+[\.\)]|[I|V|X]+[\.\)]|\b[A-Z][\.\)])\s*(.+)|(?:\*\*(.+?)\*\*)|([A-ZÀ-Ỹ0-9\s]{3,60}))\s*$",
    re.MULTILINE,
)

_SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+(?=[A-ZÀ-Ỹ0-9])")


def _is_heading_line(line: str) -> Tuple[bool, str]:
    """Determine if a line qualifies as a heading and extract its title."""
    clean = line.strip()
    if not clean:
        return False, ""

    # Markdown header
    if clean.startswith("#"):
        title = clean.lstrip("#").strip()
        return True, title

    # Bold header
    if clean.startswith("**") and clean.endswith("**") and len(clean) > 4:
        return True, clean[2:-2].strip()

    # Numbered / Alphabetic prefix like "1. Title" or "I. Title"
    match = re.match(r"^(?:(?:\d+|[IVXLCDM]+|[A-Z])[\.\)]\s+)(.+)$", clean)
    if match:
        return True, clean

    # Short title heuristic: <= 70 chars, no trailing period/semicolon/comma, starts with uppercase/number
    if len(clean) <= 70 and not clean.endswith((".", ";", ":", ",")):
        # Check if line looks like a title (e.g. capitalized)
        if clean[0].isupper() or clean[0].isdigit():
            # Avoid single short random sentence if it has verbs like "là", "được" without numbering
            if not any(stop in clean.lower() for stop in [" là ", " được ", " trong khi ", " tuy nhiên "]):
                return True, clean

    return False, ""


def split_into_sentences(text: str) -> List[str]:
    """Split Vietnamese text into discrete sentences while preserving structure."""
    lines = text.split("\n")
    sentences = []
    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue
        splits = _SENTENCE_SPLIT_REGEX.split(line_str)
        for s in splits:
            s_clean = s.strip()
            if s_clean:
                sentences.append(s_clean)
    return sentences


def chunk_vietnamese_text(
    text: str, max_chunk_chars: int = 1500, overlap_sentences: int = 2
) -> List[TextChunk]:
    """Segment Vietnamese clinical text into coherent chunks.

    Chunks respect section headers, never truncate mid-sentence, and retain
    an overlapping window of sentences between consecutive chunks to protect cross-sentence relations.
    """
    lines = text.split("\n")
    sections: List[Tuple[str, List[str]]] = []
    current_title = "General"
    current_sentences: List[str] = []

    for line in lines:
        is_hd, hd_title = _is_heading_line(line)
        if is_hd:
            if current_sentences:
                sections.append((current_title, current_sentences))
                current_sentences = []
            current_title = hd_title
        else:
            sents = split_into_sentences(line)
            current_sentences.extend(sents)

    if current_sentences:
        sections.append((current_title, current_sentences))

    chunks: List[TextChunk] = []
    chunk_id = 1
    running_char_offset = 0

    for sec_title, sents in sections:
        if not sents:
            continue

        idx = 0
        total_sents = len(sents)
        while idx < total_sents:
            current_chunk_sents: List[str] = []
            current_len = 0
            start_idx = idx

            while idx < total_sents:
                sent = sents[idx]
                sent_len = len(sent) + 1
                if current_len + sent_len > max_chunk_chars and current_chunk_sents:
                    break
                current_chunk_sents.append(sent)
                current_len += sent_len
                idx += 1

            chunk_text = " ".join(current_chunk_sents)
            end_offset = running_char_offset + len(chunk_text)

            chunks.append(
                TextChunk(
                    chunk_id=chunk_id,
                    text=chunk_text,
                    start_char=running_char_offset,
                    end_char=end_offset,
                    section_title=sec_title,
                )
            )
            chunk_id += 1
            running_char_offset = end_offset + 1

            # Apply sentence overlap for the next iteration
            if idx < total_sents and overlap_sentences > 0:
                overlap_step = max(1, idx - overlap_sentences)
                if overlap_step > start_idx:
                    idx = overlap_step

    return chunks
