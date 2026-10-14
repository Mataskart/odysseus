# Optional local judgment tool

`openjev_judge` sends one or two questions and explicitly supplied evidence to
an operator-configured local OpenJev service. When enabled and `/health` reports
a loaded engine, it is offered on agent turns whose request is a counting or
explicit OpenJev judgment (English or Lithuanian); other turns skip the health
probe. Those requests also promote plain chat into the tool-capable agent path,
after any concrete shell, web or calendar intent has had the chance to match.
Health checks have an 800 ms wall limit and are cached for 15 seconds when
healthy, 3 seconds when unavailable. Guide-only turns never probe the service.

This integration uses [lookski/openjev](https://github.com/lookski/openjev), with
the laptop's Qwen/Qwen3.5-4B causal language model and local quality adapter.
It is not an NLI-fine-tuned checkpoint, a different repository named OpenJev,
or the official TypeSafe Jev cloud service. The upstream
[engine](https://github.com/lookski/openjev/blob/49eb1382c88024e0f2550005264c13847d6ec167/openjev/core.py)
reads allowed next-token logits without generating a reasoning trace. The
laptop adapter averages two remapped option orders. Neither supplies search,
conversation history, or a guarantee that the chosen label is correct.

Configure `openjev_enabled: true` and `openjev_url: "http://192.168.1.195:8771"`
in the normal settings store. Defaults are disabled with no endpoint. Health
is checked against `openjev_model` (default `Qwen/Qwen3.5-4B`) so a
restored 0.6B rollback server is not offered as the tested quality service. The URL
accepts private/loopback literal IPs or localhost; a model cannot supply a URL.
Redirects and environment proxies are not followed. Only evidence explicitly
passed in the tool call is sent; conversation history is not attached.

For semantic counting, use `score` with consecutive levels starting at zero:

```json
{
  "state": "Present: Eglė, Tomas, Ugnė. Absent: Darius.",
  "questions": {
    "count": {
      "type": "score",
      "instructions": "How many people are present?",
      "criteria": ["Zero", "One", "Two", "Three"]
    }
  }
}
```

The returned `most_likely_level` is the discrete rubric index; `score` remains
the original fractional weighted mean. This is a model judgment, not an exact
count guarantee. Use deterministic code for literal lists, arithmetic and
counts above 9. Supply all relevant evidence without changing qualifiers or
negation. Native `choice` and `noul` are also available as optional second
opinions; `noul` returns P(Yes), and cannot express unknown.

For `choice`, `criteria` **must be a JSON object with 2..26 named options**,
never an array. Put the complete meaning in each value, not only in the key:

```json
{
  "state": "The customer says their payment was charged twice.",
  "questions": {
    "route": {
      "type": "choice",
      "instructions": "Which team should handle this message?",
      "criteria": {
        "billing": "Payment, invoice, or refund issue",
        "technical": "Software bug, integration error, or outage",
        "unknown": "The supplied message does not establish either category"
      }
    }
  }
}
```

`score` instead requires an array of 2..10 ordered descriptions. `noul` omits
`criteria` entirely. The native schema separates these three shapes so an array
cannot validate as a choice. Runtime errors identify the offending question
and include a correct object example; invalid inputs fail before network access.

Requests accept at most 6000 evidence characters, two questions, 16 KiB total,
2..26 choice options and 2..10 score levels. The service additionally enforces
2048 rendered tokens per question. Nothing is silently truncated. HTTP calls
have a 12-second wall limit and a 10-second service deadline. Rejections,
timeouts and malformed responses return an explicit failure without fabricated
answers. Returned probabilities must be finite, normalized and label-matched.

All results are advisory, uncalibrated and externally untrusted. The tool has
the same network-egress integrity gate as other model-delegation tools and
grants no authority to perform subsequent actions. A healthy endpoint makes it
available; it does not automatically execute for every message. System prompt
guidance requires delegation before answering semantic counts in supplied short
text, while literal lists, larger counts and arithmetic prefer deterministic
code. Other uses remain optional. This is a model instruction, not a hard routing
guarantee that every counting turn will call the service.
No automatic permission decisions or tool-routing classification use OpenJev.

Initial evidence: 64 synthetic English/Lithuanian cases. Focused OpenJev got
53/64 overall versus the main Qwen model's 54/64 with ~30k mixed context. Counting
was 7/8 versus 4/8, but these small samples do not establish a general accuracy
advantage. Real Odysseus task evaluation and broader counting tests remain useful.

The same saved comparison recorded presence 8/8, rubric scoring 8/8, simple
classification 7/8, quantifiers 7/8, quoted distractors 6/8, constraints 5/8, and
evidence priority 5/8. English was 30/32, Lithuanian 23/32. These are small,
synthetic samples, not calibrated production success rates. They support the
following usage guidance, included in both native and text tool prompts:

- Prefer focused semantic counting when conversation clutter makes the main
  model vulnerable; independently check the count against the supplied text.
- Optionally try simple presence/status classification and explicit short-text
  rubric scoring. Supply evidence, clear mutually distinct choices and an
  unknown option when evidence may be insufficient.
- Treat RAG relevance filtering or reranking as a candidate for a separate
  evaluation. This tool does not retrieve documents, and the existing results
  do not validate a RAG pipeline role.
- Use deterministic code for arithmetic, character/substring counts, literal
  list lengths and larger counts. Use retrieval/search for unsupported or
  current facts. Avoid delegating multi-step or temporal reasoning, conflicting
  evidence resolution, and permission, safety or high-stakes decisions.
  Explicitly requested diagnostic probes remain allowed with these limits.

Probabilities are relative preferences over the offered labels, not measured
chances of correctness. High confidence can be wrong; low confidence is a
warning, not a proven fallback threshold. A `noul` near 0.5 is inconclusive.
Report disagreements honestly, and never call an answer verified merely
because the service responded. Tool result summaries retain these limitations
so they remain visible after execution. Changing this contract does not retrain
the laptop model or improve its underlying accuracy.
