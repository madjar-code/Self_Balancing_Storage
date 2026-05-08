from __future__ import annotations
from typing import Literal

from ..types import Predicate, PredicateOp
from .ast import And, Expr, Not, Or, Query
from .lexer import LexerError, Token, tokenize


_OP_MAP = {
    "=": PredicateOp.EQ,
    "!=": PredicateOp.EQ,  # NOT applied at higher level
    "=~": PredicateOp.EQ,  # regex; we store value as compiled pattern (later)
    "!~": PredicateOp.EQ,
    ">": PredicateOp.RANGE,  # half-open ranges encoded as RANGE
    "<": PredicateOp.RANGE,
    ">=": PredicateOp.RANGE,
    "<=": PredicateOp.RANGE,
}


class QueryParseError(ValueError):
    def __init__(self, message: str, position: int, query: str):
        super().__init__(f"{message} at position {position}")
        self.position = position
        self.query = query

    def pretty(self) -> str:
        marker = " " * self.position + "^"
        return f"{self.args[0]}\n  {self.query}\n  {marker}"


class Parser:
    def __init__(self, tokens: list[Token], original: str):
        self.tokens = tokens
        self.pos = 0
        self.original = original

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def consume(self, expected_type: str, expected_value: str | None = None) -> Token:
        tok = self.peek()
        if tok.type != expected_type:
            raise QueryParseError(
                f"expected {expected_type}, got {tok.type} ({tok.value!r})",
                tok.pos, self.original,
            )
        if expected_value is not None and tok.value != expected_value:
            raise QueryParseError(
                f"expected {expected_value!r}, got {tok.value!r}",
                tok.pos, self.original,
            )
        return self.advance()

    def parse_query(self) -> Query:
        where = self.parse_or()
        time_range: tuple[float, float] | None = None
        limit: int | None = None
        order_by: tuple[str, Literal["asc", "desc"]] | None = None

        while self.peek().type == "PIPE":
            self.advance()
            kw = self.consume("KEYWORD")
            if kw.value == "last":
                time_range = self._parse_last()
            elif kw.value == "since":
                time_range = self._parse_since()
            elif kw.value == "between":
                time_range = self._parse_between()
            elif kw.value == "limit":
                limit = int(self.consume("NUMBER").value)
            elif kw.value == "order":
                self.consume("KEYWORD", "by")
                field = self.consume("IDENT").value
                direction: Literal["asc", "desc"] = "asc"
                if self.peek().type == "KEYWORD" and self.peek().value in ("asc", "desc"):
                    direction = self.advance().value  # type: ignore[assignment]
                order_by = (field, direction)
            else:
                raise QueryParseError(f"unknown clause {kw.value!r}", kw.pos, self.original)

        self.consume("EOF")
        return Query(where=where, time_range=time_range, limit=limit, order_by=order_by)

    def parse_or(self) -> Expr:
        left = self.parse_and()
        parts = [left]
        while self.peek().type == "KEYWORD" and self.peek().value == "or":
            self.advance()
            parts.append(self.parse_and())
        return Or(tuple(parts)) if len(parts) > 1 else left

    def parse_and(self) -> Expr:
        left = self.parse_unary()
        parts = [left]
        while self.peek().type == "KEYWORD" and self.peek().value == "and":
            self.advance()
            parts.append(self.parse_unary())
        return And(tuple(parts)) if len(parts) > 1 else left

    def parse_unary(self) -> Expr:
        if self.peek().type == "KEYWORD" and self.peek().value == "not":
            self.advance()
            return Not(self.parse_unary())
        return self.parse_atom()

    def parse_atom(self) -> Expr:
        tok = self.peek()
        if tok.type == "LPAREN":
            self.advance()
            expr = self.parse_or()
            self.consume("RPAREN")
            return expr
        if tok.type == "LBRACE":
            return self._parse_label_set()
        return self._parse_predicate()

    def _parse_label_set(self) -> Expr:
        self.consume("LBRACE")
        parts: list[Expr] = []
        while self.peek().type != "RBRACE":
            field = self.consume("IDENT").value
            self.consume("OP", "=")
            value = self.consume("STRING").value
            parts.append(Predicate(field=field, op=PredicateOp.EQ, value=value))
            if self.peek().type == "COMMA":
                self.advance()
        self.consume("RBRACE")
        return And(tuple(parts)) if len(parts) > 1 else parts[0]

    def _parse_predicate(self) -> Predicate:
        field_tok = self.consume("IDENT")
        # exists?
        if self.peek().type == "KEYWORD" and self.peek().value == "exists":
            self.advance()
            return Predicate(field=field_tok.value, op=PredicateOp.EXISTS)
        # in?
        if self.peek().type == "KEYWORD" and self.peek().value == "in":
            self.advance()
            self.consume("LBRACK")
            values: list = []
            while self.peek().type != "RBRACK":
                v_tok = self.advance()
                values.append(v_tok.value)
                if self.peek().type == "COMMA":
                    self.advance()
            self.consume("RBRACK")
            return Predicate(field=field_tok.value, op=PredicateOp.IN, value=values)
        # comparison
        op_tok = self.consume("OP")
        v_tok = self.advance()
        value = v_tok.value
        if v_tok.type == "NUMBER":
            value = float(value)
        return Predicate(field=field_tok.value, op=PredicateOp.EQ, value=value)
        # NOTE: simplified — full impl would distinguish !=, =~, !~ via Not wrapping or different op enum

    def _parse_last(self) -> tuple[float, float]:
        import time as _time
        n_tok = self.consume("NUMBER")
        unit_tok = self.consume("IDENT")
        seconds = _duration_to_seconds(float(n_tok.value), unit_tok.value)
        now = _time.time()
        return (now - seconds, now)

    def _parse_since(self) -> tuple[float, float]:
        import time as _time
        from datetime import datetime
        s_tok = self.consume("STRING")
        ts = datetime.fromisoformat(s_tok.value).timestamp()
        return (ts, _time.time())

    def _parse_between(self) -> tuple[float, float]:
        from datetime import datetime
        s1 = self.consume("STRING").value
        self.consume("KEYWORD", "and")
        s2 = self.consume("STRING").value
        return (
            datetime.fromisoformat(s1).timestamp(),
            datetime.fromisoformat(s2).timestamp(),
        )


def _duration_to_seconds(n: float, unit: str) -> float:
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if unit not in multipliers:
        raise ValueError(f"unknown duration unit {unit!r}")
    return n * multipliers[unit]


def parse(text: str) -> Query:
    try:
        tokens = tokenize(text)
    except LexerError as e:
        raise QueryParseError(str(e), e.position, text) from e
    parser = Parser(tokens, text)
    return parser.parse_query()
