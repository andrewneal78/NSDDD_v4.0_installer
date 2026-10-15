# -*- coding: utf-8 -*-
"""Search guidance shared by the MCP and FastAPI servers.

The score bands below come from a single-coder relevance check of Europe 2020+ results
(analysis/, Oct 2026): precision was about 14% at 0.65-0.70, 52% at 0.70-0.75 and 95% at 0.75+.
They are PROVISIONAL: re-validate before treating them as fixed, and edit them here only.
Every place that quotes these numbers (the instructions below, the tool descriptions in server.py, START HERE) must agree with
this header: 0.75 for evidence, 0.70 to explore, nothing below 0.70.
"""
from typing import Any, Dict, Iterable, List

STRONG = 0.75      # precision ~95% in validation
CANDIDATE = 0.70   # precision ~50%: read before using

SERVER_INSTRUCTIONS = """\
NSDDD semantic search: cross-lingual embedding search over national security documents.

Writing queries
- Write each query as ONE declarative sentence, phrased the way the documents themselves would state the idea \
(a commitment, requirement, arrangement, assessment or definition). Do not write questions or keyword strings.
- Use specific terms of the topic (named instruments, institutions, legal terms, actors, objects). Vague umbrella \
words such as security, crisis or threat attract generic text unless they are the topic itself.
- To cover a topic, run 3-5 queries that differ in vocabulary and level of detail, not only word order.

Reading scores (provisional, from a validation on Europe results)
- score >= 0.75: usually relevant (about 95% judged relevant)
- 0.70-0.75: mixed (about half judged relevant); read the passage before using it. The default threshold, 0.72, \
sits in this band: use 0.75 when you need evidence and 0.70 when you are exploring
- below 0.70: mostly noise (about 14% relevant)
- Quality varies by query. Before relying on a query, read about 10 results at >= 0.70; if fewer than about \
40% are on topic, reword it with more concrete anchors.
- Each result carries a `confidence` field, and the response has `score_bands` and `search_notes`.

Counting and comparing
- Each passage counts once: when the original-language text and its English translation both match, they are merged \
into the English result (`pairs_merged` says how many). Original-language results that remain are passages whose \
English did not match; they are genuine hits and count. Pass count_passages_once=false to count both sides.
- `result_limit` only limits what is returned inline; `num_results` is the full count.
- Compare countries per segment of their documents, not by raw counts: long or numerous documents dominate.
- A topic not being retrieved is not evidence that a country lacks it. Check which documents the country \
has first.

Tools: semantic_search is the main search tool and the default for every topic. keyword_search is only for \
literal terms (an exact name or phrase); it returns no confidence or score bands.

Workflow: call filter_options once, apply filters (regions, year_min, doc_types), run semantic_search, read the top \
results, discard off-topic ones, then summarise.
"""

FORMULATE_PROMPT = """\
You write semantic search queries for the NSDDD, a corpus of national security and defence documents. The search \
is multilingual: a query in any language matches original-language and English text. Given the research topic \
below, write 3-5 queries.

Rules:
1. Each query is one declarative sentence, written the way the documents themselves would state the idea (for \
example a commitment, a requirement, an assessment, a definition, or a description of an arrangement). Choose the \
form that matches what I am looking for. No questions or keyword lists.
2. Use the specific terms of the topic: named instruments, institutions, legal terms, actors, objects. Vague \
umbrella words (security, crisis, threat) attract generic text unless they are the topic itself.
3. Vary the queries in vocabulary and level of detail, not just word order. For example: a general statement, \
a version in institutional or legal terms, a version in operational terms, and a version using the terms another \
type of state might use.
4. Keep each query centred on one subject. Combining closely linked terms is fine when documents usually state \
them together.

For each query give: the sentence; one line describing a passage that should match; and one kind of passage that \
might match wrongly. Say which queries are most likely to be noisy.
Suggest filters (region, years, document type) only if the topic implies them.
After running the queries, read about 10 results at score >= 0.70 for each one, and drop or reword any query whose \
results are mostly off topic. Score meanings are in the server instructions.

Research topic: {topic}
"""


def confidence(score: float) -> str:
    return 'strong' if score >= STRONG else 'candidate' if score >= CANDIDATE else 'weak'


def annotate(response: Dict[str, Any], scores: Iterable[float]) -> Dict[str, Any]:
    """Add score-band counts and plain-language notes to a semantic_search response (in place)."""
    scores = [float(s) for s in scores]
    bands = {'strong': 0, 'candidate': 0, 'weak': 0}
    for s in scores:
        bands[confidence(s)] += 1
    for row in response.get('results', []):
        row['confidence'] = confidence(row['score'])
    notes: List[str] = []
    n = len(scores)
    if n == 0:
        notes.append('No results. Try a wording closer to how documents state the measure, or lower search_threshold '
                     'to 0.65 for exploration only (results below 0.70 are mostly noise).')
    else:
        notes.append(f"{bands['strong']} strong (>= {STRONG}), {bands['candidate']} candidate "
                     f"({CANDIDATE}-{STRONG}), {bands['weak']} weak (< {CANDIDATE}) of {n} results.")
        if bands['strong'] == 0:
            notes.append('No strong evidence: treat every result as a lead to read, not a finding. Consider rewording '
                         'with more concrete terms, or a different framing, before drawing conclusions.')
        if bands['weak'] > bands['strong'] + bands['candidate']:
            notes.append('Most results are below 0.70 and likely off-topic; raise search_threshold to 0.70 or higher.')
    notes.append('Confidence bands are provisional (validated on Europe results). Cross-check passages that '
                 'several differently-worded queries return.')
    response['score_bands'] = bands
    response['search_notes'] = notes
    return response
