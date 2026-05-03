from __future__ import annotations


class StabilityCounter:
    def __init__(self, n: int = 3):
        self.n = n
        self.count = 0

    def observe(self, condition: bool) -> bool:
        if condition:
            self.count = min(self.count + 1, self.n)
        else:
            self.count = max(self.count - 1, 0)
        return self.count >= self.n

    def reset(self) -> None:
        self.count = 0
