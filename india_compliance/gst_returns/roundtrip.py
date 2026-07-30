_MISSING = object()


def _clean(value, precision):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), precision)
    if isinstance(value, dict):
        return {k: _clean(v, precision) for k, v in value.items() if not _is_empty(v)}
    if isinstance(value, (list, tuple)):
        return [_clean(v, precision) for v in value]
    return value


def _is_empty(value):
    # drop falsy, keep 0 and False
    return not (value or value == 0)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _first_diff(a, b, path="root"):
    """Return first difference between a and b, or None if equal"""
    if type(a) is not type(b) and not (_is_number(a) and _is_number(b)):
        return (path, a, b)

    if isinstance(a, dict):
        for key in a.keys() | b.keys():
            av, bv = a.get(key, _MISSING), b.get(key, _MISSING)
            if av is _MISSING or bv is _MISSING:
                return (f"{path}.{key}", av, bv)
            if diff := _first_diff(av, bv, f"{path}.{key}"):
                return diff
        return None

    if isinstance(a, list):
        if len(a) != len(b):
            return (f"{path}[len]", len(a), len(b))
        for i, (av, bv) in enumerate(zip(a, b, strict=True)):
            if diff := _first_diff(av, bv, f"{path}[{i}]"):
                return diff
        return None

    return None if a == b else (path, a, b)


def assert_roundtrip(original, roundtripped, precision=2):
    """Raise if roundtrip lost data. Path in message."""
    diff = _first_diff(_clean(original, precision), _clean(roundtripped, precision))
    if diff:
        path, a, b = diff
        raise AssertionError(f"round-trip mismatch at {path}: {a!r} != {b!r}")
