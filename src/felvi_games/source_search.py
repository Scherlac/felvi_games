"""Source text search and retrieval utilities for task/guide verification."""

from __future__ import annotations

import re
from typing import Any

from felvi_games.config import resolve_asset


def search_source_text(
    relative_path: str,
    query: str,
    *,
    max_hits: int = 20,
    case_sensitive: bool = False,
    context_lines: int = 2,
) -> dict[str, Any]:
    """Search for query in source text file and return matching lines with context.
    
    Args:
        relative_path: relative asset path, e.g., "text/A8_2020_2_ut.txt"
        query: search string (plain text or regex-like)
        max_hits: maximum number of matches to return
        case_sensitive: whether search is case-sensitive
        context_lines: lines of context before/after each match
    
    Returns:
        {
            "status": "found" | "not_found" | "error",
            "file_path": str,
            "query": str,
            "match_count": int,
            "total_lines": int,
            "matches": [
                {
                    "line_number": int (1-indexed),
                    "line_text": str,
                    "context_before": list[str],
                    "context_after": list[str],
                },
                ...
            ],
            "error": str | None,
        }
    """
    try:
        asset_path = resolve_asset(relative_path)
        if not asset_path.exists():
            return {
                "status": "error",
                "file_path": str(asset_path),
                "query": query,
                "match_count": 0,
                "error": f"Source file not found: {asset_path}",
            }
        
        text_content = asset_path.read_text(encoding="utf-8")
        lines = text_content.split("\n")
        
        query_str = str(query or "").strip()
        if not query_str:
            return {
                "status": "error",
                "file_path": str(asset_path),
                "query": query,
                "match_count": 0,
                "total_lines": len(lines),
                "error": "Empty query string",
            }
        
        # Compile regex or escape for literal search
        try:
            if case_sensitive:
                pattern = re.compile(query_str)
            else:
                pattern = re.compile(query_str, re.IGNORECASE)
        except re.error:
            # Fallback to literal search on invalid regex
            if case_sensitive:
                pattern = re.compile(re.escape(query_str))
            else:
                pattern = re.compile(re.escape(query_str), re.IGNORECASE)
        
        matches = []
        for i, line in enumerate(lines):
            if pattern.search(line):
                context_before = lines[max(0, i - context_lines) : i]
                context_after = lines[i + 1 : min(len(lines), i + context_lines + 1)]
                matches.append({
                    "line_number": i + 1,  # 1-indexed
                    "line_text": line,
                    "context_before": context_before,
                    "context_after": context_after,
                })
                if len(matches) >= max_hits:
                    break
        
        status = "found" if matches else "not_found"
        return {
            "status": status,
            "file_path": str(asset_path),
            "query": query,
            "match_count": len(matches),
            "total_lines": len(lines),
            "matches": matches,
        }
    
    except Exception as exc:
        return {
            "status": "error",
            "file_path": relative_path,
            "query": query,
            "match_count": 0,
            "error": f"Search failed: {exc}",
        }


def get_source_window(
    relative_path: str,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    """Retrieve a window of lines from source text file.
    
    Args:
        relative_path: relative asset path
        start_line: 1-indexed start line number (inclusive)
        end_line: 1-indexed end line number (inclusive)
    
    Returns:
        {
            "status": "ok" | "error",
            "file_path": str,
            "start_line": int,
            "end_line": int,
            "total_lines": int,
            "lines": list[str],
            "error": str | None,
        }
    """
    try:
        asset_path = resolve_asset(relative_path)
        if not asset_path.exists():
            return {
                "status": "error",
                "file_path": str(asset_path),
                "start_line": start_line,
                "end_line": end_line,
                "error": f"Source file not found: {asset_path}",
            }
        
        text_content = asset_path.read_text(encoding="utf-8")
        lines = text_content.split("\n")
        total_lines = len(lines)
        
        # Normalize 1-indexed input to 0-indexed slice
        start_idx = max(0, min(start_line - 1, total_lines - 1))
        end_idx = max(0, min(end_line, total_lines))
        
        retrieved_lines = lines[start_idx:end_idx]
        
        return {
            "status": "ok",
            "file_path": str(asset_path),
            "start_line": start_line,
            "end_line": end_line,
            "total_lines": total_lines,
            "actual_start": start_idx + 1,
            "actual_end": min(end_idx, total_lines),
            "lines": retrieved_lines,
        }
    
    except Exception as exc:
        return {
            "status": "error",
            "file_path": relative_path,
            "start_line": start_line,
            "end_line": end_line,
            "error": f"Retrieval failed: {exc}",
        }


def find_task_in_sources(
    feladat_id: str,
    task_sheet_path: str | None = None,
    guide_path: str | None = None,
    context_lines: int = 3,
) -> dict[str, Any]:
    """Locate a task by ID in source files using task number and subtask letter.
    
    Attempts to find patterns like:
    - "8." for task number 8
    - "a)" or "a/" for subtask a
    - and returns surrounding lines for verification.
    """
    import re
    
    try:
        # Parse feladat_id to extract task number and subtask
        # Example: mag4_2020_2_8_a -> task 8, subtask a
        match = re.search(r"_(\d+)_([a-z])?$", feladat_id)
        if not match:
            return {
                "status": "error",
                "feladat_id": feladat_id,
                "error": f"Cannot parse task/subtask from ID: {feladat_id}",
            }
        
        task_num = match.group(1)
        subtask_letter = match.group(2)
        
        results = {
            "status": "ok",
            "feladat_id": feladat_id,
            "task_number": task_num,
            "subtask_letter": subtask_letter,
            "task_sheet": None,
            "guide": None,
        }
        
        # Search in task sheet
        if task_sheet_path:
            heading_patterns = [
                rf"^\s*{re.escape(task_num)}\.",  # "8."
                rf"^\s*{re.escape(task_num)}\s*\.",  # "8 ."
                rf"{re.escape(task_num)}\.\s*",  # inline "8. "
            ]
            
            task_sheet_result = None
            for pattern in heading_patterns:
                result = search_source_text(
                    task_sheet_path,
                    pattern,
                    max_hits=5,
                    context_lines=context_lines,
                )
                if result.get("match_count", 0) > 0:
                    task_sheet_result = result
                    break
            
            results["task_sheet"] = task_sheet_result
        
        # Search in guide
        if guide_path:
            if subtask_letter:
                guide_patterns = [
                    rf"^\s*{re.escape(subtask_letter)}\)",  # "a)"
                    rf"^\s*{re.escape(subtask_letter)}/",   # "a/"
                    rf"^\s*{re.escape(subtask_letter)}\.",   # "a."
                    rf"{re.escape(task_num)}\.\s*{re.escape(subtask_letter)}\)",  # "8.a)"
                ]
            else:
                guide_patterns = [
                    rf"^\s*{re.escape(task_num)}\.",
                    rf"{re.escape(task_num)}\.\s*",
                ]
            
            guide_result = None
            for pattern in guide_patterns:
                result = search_source_text(
                    guide_path,
                    pattern,
                    max_hits=5,
                    context_lines=context_lines,
                )
                if result.get("match_count", 0) > 0:
                    guide_result = result
                    break
            
            results["guide"] = guide_result
        
        return results
    
    except Exception as exc:
        return {
            "status": "error",
            "feladat_id": feladat_id,
            "error": f"Task lookup failed: {exc}",
        }


def compare_excerpt_to_source(
    stored_excerpt: str,
    source_path: str,
    context_lines: int = 2,
) -> dict[str, Any]:
    """Check if stored excerpt matches any section in source file.
    
    Returns confidence score and potential mismatch reasons.
    """
    try:
        excerpt_clean = (stored_excerpt or "").strip()
        if not excerpt_clean:
            return {
                "status": "error",
                "error": "Empty stored excerpt",
            }
        
        asset_path = resolve_asset(source_path)
        if not asset_path.exists():
            return {
                "status": "error",
                "error": f"Source file not found: {asset_path}",
            }
        
        text_content = asset_path.read_text(encoding="utf-8")
        
        # Try exact substring match
        if excerpt_clean in text_content:
            lines = text_content.split("\n")
            for i, line in enumerate(lines):
                if excerpt_clean in line:
                    context_before = lines[max(0, i - context_lines) : i]
                    context_after = lines[i + 1 : min(len(lines), i + context_lines + 1)]
                    return {
                        "status": "found",
                        "match_type": "exact",
                        "confidence": 1.0,
                        "line_number": i + 1,
                        "context_before": context_before,
                        "context_after": context_after,
                        "note": "Exact substring match found in source",
                    }
        
        # Try fuzzy substring match (first 50 chars, last 50 chars)
        excerpt_lines = excerpt_clean.split("\n")
        first_line = (excerpt_lines[0] or "").strip()
        if first_line:
            result = search_source_text(
                source_path,
                re.escape(first_line[:30]),
                max_hits=3,
                case_sensitive=False,
                context_lines=context_lines,
            )
            if result.get("match_count", 0) > 0:
                return {
                    "status": "partial",
                    "match_type": "first_line_partial",
                    "confidence": 0.5,
                    "note": "First line of excerpt found in source, but not exact match",
                    "search_result": result,
                }
        
        return {
            "status": "not_found",
            "match_type": "none",
            "confidence": 0.0,
            "note": (
                "Excerpt not found in source file; may be from different guide "
                "version or incorrect source reference"
            ),
        }
    
    except Exception as exc:
        return {
            "status": "error",
            "error": f"Comparison failed: {exc}",
        }
