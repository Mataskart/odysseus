"""Search the permitted tool catalog without executing discovered tools."""

import asyncio
import json
import re


async def discover_tools(content, schemas, disabled_tools):
    try:
        args = json.loads(content)
        query = args.get("query", "")
        limit = args.get("limit", 5)
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 1000:
            raise ValueError("query must contain 1..1000 characters")
        if type(limit) is not int or not 1 <= limit <= 8:
            raise ValueError("limit must be an integer from 1 to 8")
    except (ValueError, TypeError, AttributeError) as error:
        return "find_tools: invalid", {"error": str(error), "exit_code": 1}

    catalog = {
        schema["function"]["name"]: schema["function"]
        for schema in schemas
        if schema.get("function", {}).get("name")
        and schema["function"]["name"] not in disabled_tools
        and schema["function"]["name"] != "find_tools"
    }
    from src.tool_index import ToolIndex, get_tool_index

    def retrieve():
        return get_tool_index().retrieve(query, k=32)

    try:
        ranked = await asyncio.wait_for(asyncio.to_thread(retrieve), timeout=2)
        method = "rag"
    except Exception:
        ranked = []
        method = "lexical_fallback"

    words = set(re.findall(r"\w+", query.lower()))
    lexical = sorted(catalog, key=lambda name: (
        -len(words & set(re.findall(r"\w+", name.replace("_", " ") + " " + catalog[name].get("description", "").lower()))),
        name,
    ))
    exact = [name for name in catalog if name.lower() in words]
    hinted = ToolIndex.keyword_tools_for_query(query)
    candidates = list(dict.fromkeys(exact + hinted + ranked + [
        name for name in lexical
        if words & set(re.findall(r"\w+", name.replace("_", " ") + " " + catalog[name].get("description", "").lower()))
    ]))
    names = [name for name in candidates if name in catalog][:limit]
    matches = [{"name": name, "description": catalog[name].get("description", "")[:500]} for name in names]
    output = {"tools": matches, "method": method,
              "message": (
                  "These candidate tools are available on the next round. Check their descriptions: "
                  "a match does not prove the requested integration or capability exists. "
                  "Call a suitable tool to do the work rather than rediscovering it."
                  if names else
                  "No permitted matching tools found for this query. Do not just rephrase the same capability. "
                  "Use an explicit alternative or a genuinely different capability if relevant; "
                  "otherwise report that discovery found no matching permitted tool."
              )}
    return "find_tools: " + query[:80], {
        "output": json.dumps(output, ensure_ascii=False), "discovered_tools": names, "exit_code": 0,
    }
