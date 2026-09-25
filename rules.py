OPERATORS = {
    "gt": lambda value, threshold: value > threshold,
    "gte": lambda value, threshold: value >= threshold,
    "lt": lambda value, threshold: value < threshold,
    "lte": lambda value, threshold: value <= threshold,
    "eq": lambda value, threshold: value == threshold,
}


def evaluate(value: float, operator: str, threshold: float) -> bool:
    try:
        fn = OPERATORS[operator]
    except KeyError:
        raise ValueError(f"Unknown operator: {operator}")
    return fn(value, threshold)
