# Recoverable tool discovery

`find_tools` supplements the existing initial tool selector. In normal agent mode it remains available even when the selected domain misses a capability. The main model supplies a focused query using relevant conversation context. No extra routing model or OpenJev call is required.

The tool searches the existing ToolIndex (up to two seconds), prioritizes exact tool names, and falls back to catalog text matching. It returns at most eight permitted tools (five by default). Successful matches join the current run's selection for subsequent rounds, including fallback routes. Discovery itself never executes a matched tool.

The catalog consists of built-in schemas and the current run's enabled MCP schemas. Disabled tools, owner restrictions, guide-only mode, and plan-mode restrictions remain enforced. Discovery does not change settings or grant execution approval. Returned descriptions are treated as untrusted data, including MCP descriptions.

Example: a request to “suggest improvements” initially receives document tools. The model can call `find_tools` with `{"query":"read_file grep inspect local OpenJev configuration"}`, then call the returned file tools on the next round. Existing domain pruning still applies to the initial selection; it does not remove tools discovered during that run.

Discovery depends on the model choosing to call it. It does not guarantee task completion, replace the bounded stall recovery, or change specialized fine-tuned model modes that deliberately disable native tools. Tool selection and calls are recorded in the existing per-round logs.
