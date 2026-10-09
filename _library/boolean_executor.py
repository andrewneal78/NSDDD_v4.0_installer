"""
Boolean query executor for NSDDD v3 search.

Walks a parsed AST (from boolean_parser) and evaluates it against
a model dictionary using a caller-supplied keyword search function.
"""

from __future__ import annotations
from typing import Callable

from _library.boolean_parser import TermNode, AndNode, OrNode, NotNode, Node


# Type alias for search results
SearchResults = list[tuple[str, float]]


class BooleanQueryExecutor:
    """
    Execute a boolean query AST against a model dictionary.

    Args:
        model_dict: The loaded model data dictionary (passed through to
            keyword_search_func unchanged).
        keyword_search_func: Callable(term: str, model_dict: dict) →
            List[Tuple[str, float]].  Returns (segment_id, score) pairs.
        scoring_strategy: How to combine scores when merging results.
            - 'match_count': sum of scores (default)
            - 'avg_score':   average of scores
            - 'max_score':   maximum score
    """

    STRATEGIES = ('match_count', 'avg_score', 'max_score')

    def __init__(
        self,
        model_dict: dict,
        keyword_search_func: Callable,
        scoring_strategy: str = 'match_count',
    ):
        if scoring_strategy not in self.STRATEGIES:
            raise ValueError(
                f'Unknown scoring_strategy "{scoring_strategy}". '
                f'Choose from {self.STRATEGIES}'
            )
        self.model_dict = model_dict
        self.keyword_search_func = keyword_search_func
        self.scoring_strategy = scoring_strategy

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(self, ast: Node) -> SearchResults:
        """
        Walk the AST and return a scored list of (segment_id, score) tuples.

        Args:
            ast: Root node of the parsed boolean AST.

        Returns:
            List of (segment_id, score) tuples, sorted descending by score.
        """
        result_dict = self._eval(ast)
        results = sorted(result_dict.items(), key=lambda x: x[1], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Internal evaluation
    # ------------------------------------------------------------------

    def _eval(self, node: Node) -> dict[str, float]:
        """Recursively evaluate a node, returning {segment_id: score}."""
        if isinstance(node, TermNode):
            return self._eval_term(node)
        if isinstance(node, NotNode):
            return self._eval_not(node)
        if isinstance(node, AndNode):
            return self._eval_and(node)
        if isinstance(node, OrNode):
            return self._eval_or(node)
        raise TypeError(f'Unknown node type: {type(node)}')

    def _eval_term(self, node: TermNode) -> dict[str, float]:
        results = self.keyword_search_func(node.term, self.model_dict)
        return dict(results)

    def _eval_not(self, node: NotNode) -> dict[str, float]:
        # "All segments" means: the union of everything evaluated so far
        # vs what the sub-expression matches.  Here we return an empty
        # dict whose complement is computed by the parent AND/OR context.
        # In practice, NOT at the top level returns empty (nothing to
        # subtract from).  It is most useful as: X AND NOT Y.
        matching = self._eval(node.operand)
        # Caller (AndNode) subtracts these; we flag them with negative score
        # so AND can identify them.  Use a sentinel value.
        return {seg_id: float('-inf') for seg_id in matching}

    def _eval_and(self, node: AndNode) -> dict[str, float]:
        left = self._eval(node.left)
        right = self._eval(node.right)

        # Handle NOT on either side: subtract rather than intersect
        if _is_not_result(left):
            # left is NOT expression — keep right minus left keys
            excluded = set(left.keys())
            return {k: v for k, v in right.items() if k not in excluded}

        if _is_not_result(right):
            excluded = set(right.keys())
            return {k: v for k, v in left.items() if k not in excluded}

        # Standard intersection: keep only keys present in both
        common = set(left.keys()) & set(right.keys())
        return {
            seg_id: self._combine(left[seg_id], right[seg_id])
            for seg_id in common
        }

    def _eval_or(self, node: OrNode) -> dict[str, float]:
        left = self._eval(node.left)
        right = self._eval(node.right)

        merged: dict[str, float] = dict(left)
        for seg_id, score in right.items():
            if seg_id in merged:
                merged[seg_id] = self._combine(merged[seg_id], score)
            else:
                merged[seg_id] = score
        return merged

    def _combine(self, a: float, b: float) -> float:
        if self.scoring_strategy == 'max_score':
            return max(a, b)
        if self.scoring_strategy == 'avg_score':
            return (a + b) / 2.0
        # Default: match_count / sum
        return a + b


def _is_not_result(d: dict[str, float]) -> bool:
    """Return True if dict represents a NOT result (all values are -inf)."""
    return bool(d) and all(v == float('-inf') for v in d.values())


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def execute_boolean_query(
    ast: Node,
    model_dict: dict,
    keyword_search_func: Callable,
    scoring_strategy: str = 'match_count',
) -> SearchResults:
    """
    Execute a boolean query AST and return scored results.

    Args:
        ast: Parsed boolean AST (from parse_boolean_query).
        model_dict: Model data dictionary.
        keyword_search_func: Callable(term, model_dict) → [(seg_id, score)].
        scoring_strategy: 'match_count' | 'avg_score' | 'max_score'.

    Returns:
        List of (segment_id, score) tuples, sorted descending by score.
    """
    return BooleanQueryExecutor(
        model_dict, keyword_search_func, scoring_strategy
    ).execute(ast)
