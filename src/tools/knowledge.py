"""Search indexed personal and shared documents with the authenticated owner."""

import asyncio
import json

from src.rag_singleton import get_rag_manager


async def search_knowledge(content, owner=None):
    if not isinstance(owner, str) or not owner.strip():
        return {"error": "An authenticated account is required.", "exit_code": 1}
    try:
        args = json.loads(content)
        query = args.get("query", "")
        limit = args.get("limit", 5)
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 2000:
            raise ValueError("query must contain 1..2000 characters")
        if type(limit) is not int or not 1 <= limit <= 8:
            raise ValueError("limit must be an integer from 1 to 8")
    except (ValueError, TypeError, AttributeError) as error:
        return {"error": str(error), "exit_code": 1}

    try:
        manager = await asyncio.to_thread(get_rag_manager)
        if manager is None or not manager.healthy:
            return {"error": "The indexed document search is unavailable.", "retrieval": {"outcome": "unavailable"}, "exit_code": 1}
        results = await asyncio.to_thread(manager.search, query.strip(), k=limit, owner=owner, raise_on_error=True)
    except Exception:
        return {"error": "The indexed document search failed. Try again later.", "retrieval": {"outcome": "unavailable"}, "exit_code": 1}

    relevant = [result for result in results if result.get("similarity", 0) >= 0.35]
    retrieval = {"outcome": "retrieved" if relevant else "below_threshold" if results else "no_matches",
                 "result_count": len(results), "relevant_count": len(relevant), "threshold": 0.35}
    sources = []
    for result in relevant[:limit]:
        metadata = result.get("metadata") or {}
        document = str(result.get("document") or "")
        sources.append({
            "id": result.get("id"),
            "filename": metadata.get("filename") or metadata.get("source") or "unknown",
            "content": document[:4000],
            "truncated": len(document) > 4000,
            "similarity": result.get("similarity"),
        })
    return {
        "retrieval": retrieval,
        "output": json.dumps({
            "retrieval": retrieval,
            "sources": sources,
            "message": "Cite the returned filenames and use only relevant passages. Search again with focused topic terms if necessary; filenames need not contain the topic. No matches do not prove the material is absent.",
        }, ensure_ascii=False),
        "exit_code": 0,
    }
