from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Union

from ..types import Predicate


@dataclass(frozen=True)
class And:
    parts: tuple["Expr", ...]


@dataclass(frozen=True)
class Or:
    parts: tuple["Expr", ...]


@dataclass(frozen=True)
class Not:
    expr: "Expr"


Expr = Union[Predicate, And, Or, Not]


@dataclass(frozen=True)
class Query:
    where: Expr
    time_range: tuple[float, float] | None = None
    limit: int | None = None
    order_by: tuple[str, Literal["asc", "desc"]] | None = None
