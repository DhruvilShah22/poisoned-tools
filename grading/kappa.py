"""Cohen's kappa for blind-grader validation (same estimator as paper 1)."""

from collections import Counter


def cohen_kappa(pairs: list[tuple]) -> float:
    n = len(pairs)
    if n == 0:
        return 1.0
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0
