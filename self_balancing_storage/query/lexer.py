from __future__ import annotations
from dataclasses import dataclass


KEYWORDS = {
    "and", "or", "not", "in", "exists",
    "last", "since", "between", "limit", "order", "by", "asc", "desc",
}

DURATION_UNITS = {"s", "m", "h", "d"}


@dataclass(frozen=True)
class Token:
    type: str  # IDENT, KEYWORD, STRING, NUMBER, OP, LPAREN, RPAREN, LBRACE, RBRACE, LBRACK, RBRACK, COMMA, PIPE, EOF
    value: str
    pos: int


class LexerError(ValueError):
    def __init__(self, message: str, position: int):
        super().__init__(message)
        self.position = position


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    pos = 0
    while pos < len(text):
        c = text[pos]
        if c.isspace():
            pos += 1
            continue
        if c.isalpha() or c == "_":
            t, pos = _read_identifier(text, pos)
            tokens.append(t)
        elif c.isdigit() or (c == "-" and pos + 1 < len(text) and text[pos + 1].isdigit()):
            t, pos = _read_number(text, pos)
            tokens.append(t)
        elif c == '"':
            t, pos = _read_string(text, pos)
            tokens.append(t)
        elif c in "=!<>~":
            t, pos = _read_operator(text, pos)
            tokens.append(t)
        elif c == "(":
            tokens.append(Token("LPAREN", "(", pos))
            pos += 1
        elif c == ")":
            tokens.append(Token("RPAREN", ")", pos))
            pos += 1
        elif c == "{":
            tokens.append(Token("LBRACE", "{", pos))
            pos += 1
        elif c == "}":
            tokens.append(Token("RBRACE", "}", pos))
            pos += 1
        elif c == "[":
            tokens.append(Token("LBRACK", "[", pos))
            pos += 1
        elif c == "]":
            tokens.append(Token("RBRACK", "]", pos))
            pos += 1
        elif c == ",":
            tokens.append(Token("COMMA", ",", pos))
            pos += 1
        elif c == "|":
            tokens.append(Token("PIPE", "|", pos))
            pos += 1
        else:
            raise LexerError(f"unexpected character {c!r}", pos)
    tokens.append(Token("EOF", "", pos))
    return tokens


def _read_identifier(text: str, start: int) -> tuple[Token, int]:
    end = start
    while end < len(text) and (text[end].isalnum() or text[end] == "_"):
        end += 1
    word = text[start:end]
    type_ = "KEYWORD" if word in KEYWORDS else "IDENT"
    return Token(type_, word, start), end


def _read_number(text: str, start: int) -> tuple[Token, int]:
    end = start
    if text[end] == "-":
        end += 1
    while end < len(text) and (text[end].isdigit() or text[end] == "."):
        end += 1
    # Check for duration suffix
    if end < len(text) and text[end] in DURATION_UNITS:
        # Combine number with unit (e.g., "1h" stays as one NUMBER token w/ unit?)
        # For simplicity: emit number, then the parser checks if next token is a unit IDENT
        pass
    return Token("NUMBER", text[start:end], start), end


def _read_string(text: str, start: int) -> tuple[Token, int]:
    # text[start] == '"'
    end = start + 1
    while end < len(text) and text[end] != '"':
        if text[end] == "\\":
            end += 2
        else:
            end += 1
    if end >= len(text):
        raise LexerError("unterminated string", start)
    value = text[start + 1:end]
    return Token("STRING", value, start), end + 1


def _read_operator(text: str, start: int) -> tuple[Token, int]:
    # Two-char operators first
    if start + 1 < len(text):
        two = text[start:start + 2]
        if two in {"==", "!=", "<=", ">=", "=~", "!~"}:
            op_norm = "=" if two == "==" else two
            return Token("OP", op_norm, start), start + 2
    # Single-char
    c = text[start]
    if c == "=":
        return Token("OP", "=", start), start + 1
    if c in "<>":
        return Token("OP", c, start), start + 1
    raise LexerError(f"unexpected operator {c!r}", start)
