"""
Boolean query parser for NSDDD v3 search.

Parses boolean search queries into an AST for evaluation.

Supported operators:
  AND  (or &)  — both terms must appear
  OR   (or |)  — either term must appear
  NOT  (or !)  — prefix negation
  ()           — grouping / precedence
  "..."        — quoted phrase (passed through as a single TermNode)
  * ?          — wildcards (passed through to TermNode)

Operator precedence (lowest to highest): OR < AND < NOT < atoms
"""

from __future__ import annotations
from dataclasses import dataclass
import re


# ---------------------------------------------------------------------------
# AST node types
# ---------------------------------------------------------------------------

@dataclass
class TermNode:
    """Leaf node representing a single search term (may contain wildcards)."""
    term: str


@dataclass
class NotNode:
    """Unary NOT node."""
    operand: 'Node'


@dataclass
class AndNode:
    """Binary AND node."""
    left: 'Node'
    right: 'Node'


@dataclass
class OrNode:
    """Binary OR node."""
    left: 'Node'
    right: 'Node'


Node = TermNode | NotNode | AndNode | OrNode


# ---------------------------------------------------------------------------
# Tokeniser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r'"[^"]*"'           # quoted phrase
    r"|\u201c[^\u201d]*\u201d"          # curly double quotes
    r"|(?<![\w])'[^']+'(?![\w])"      # single-quoted phrase (not an apostrophe)
    r"|(?<![\w])\u2018[^\u2019]+\u2019(?![\w])"  # curly single quotes
    r'|[()]'             # parentheses
    r'|[!&|]'            # single-char operators
    r'|[^\s()!&|]+'      # bare word (may include wildcards * ?)
)


def _tokenise(query: str):
    """Return list of token strings from query."""
    return _TOKEN_RE.findall(query)


_QUOTES = {'"': '"', "'": "'", '\u201c': '\u201d', '\u2018': '\u2019'}


def _is_quoted(tok: str) -> bool:
    return len(tok) >= 2 and _QUOTES.get(tok[0]) == tok[-1]


def _normalise_token(tok: str) -> str:
    """Normalise operator spelling to canonical form."""
    upper = tok.upper()
    if upper == 'AND':
        return 'AND'
    if upper == 'OR':
        return 'OR'
    if upper in ('NOT', '!'):
        return 'NOT'
    if tok == '&':
        return 'AND'
    if tok == '|':
        return 'OR'
    return tok


# ---------------------------------------------------------------------------
# Recursive-descent parser
# ---------------------------------------------------------------------------

class BooleanQueryParser:
    """
    Recursive-descent parser for boolean search queries.

    Grammar (lowest precedence first):
        expr   ::= and_expr ( OR and_expr )*
        and_expr ::= not_expr ( AND not_expr )*
        not_expr ::= NOT not_expr | atom
        atom   ::= '(' expr ')' | TERM
    """

    def parse(self, query: str) -> Node:
        """
        Parse a boolean query string into an AST.

        Args:
            query: Query string with optional AND/OR/NOT operators.

        Returns:
            Root AST node.

        Raises:
            ValueError: If the query is empty or syntactically invalid.
        """
        query = query.strip()
        if not query:
            raise ValueError('Empty query')

        tokens = _tokenise(query)
        self._tokens = [_normalise_token(t) for t in tokens]
        self._pos = 0

        node = self._parse_or()

        if self._pos < len(self._tokens):
            raise ValueError(
                f'Unexpected token at position {self._pos}: '
                f'"{self._tokens[self._pos]}"'
            )

        return node

    # ------------------------------------------------------------------
    def _peek(self) -> str | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _consume(self, expected: str | None = None) -> str:
        tok = self._tokens[self._pos]
        if expected is not None and tok != expected:
            raise ValueError(f'Expected "{expected}", got "{tok}"')
        self._pos += 1
        return tok

    # ------------------------------------------------------------------
    def _parse_or(self) -> Node:
        left = self._parse_and()
        while self._peek() == 'OR':
            self._consume('OR')
            right = self._parse_and()
            left = OrNode(left, right)
        return left

    def _parse_and(self) -> Node:
        left = self._parse_not()
        while self._peek() == 'AND':
            self._consume('AND')
            right = self._parse_not()
            left = AndNode(left, right)
        return left

    def _parse_not(self) -> Node:
        if self._peek() == 'NOT':
            self._consume('NOT')
            operand = self._parse_not()
            return NotNode(operand)
        return self._parse_atom()

    def _parse_atom(self) -> Node:
        tok = self._peek()
        if tok is None:
            raise ValueError('Unexpected end of query')

        if tok == '(':
            self._consume('(')
            node = self._parse_or()
            self._consume(')')
            return node

        if tok in (')', 'AND', 'OR', 'NOT'):
            raise ValueError(f'Unexpected token "{tok}" where term expected')

        self._pos += 1
        if _is_quoted(tok):
            return TermNode(tok[1:-1].strip())
        # Adjacent bare words (African Union) form one phrase
        words = [tok]
        while True:
            nxt = self._peek()
            if (nxt is None or nxt in ('(', ')', 'AND', 'OR', 'NOT')
                    or nxt in ('!', '&', '|') or _is_quoted(nxt)):
                break
            words.append(nxt)
            self._pos += 1
        return TermNode(' '.join(words))


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def parse_boolean_query(query: str) -> Node:
    """
    Parse a boolean search query string into an AST.

    Args:
        query: Boolean query string.

    Returns:
        Root AST node.
    """
    return BooleanQueryParser().parse(query)
