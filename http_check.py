"""HTTP-перевірка через веб-проксі: два послідовні запити та аналіз лічильника відвідувань."""

import json

import requests


def probe(url, timeout):
    result = {"status": None, "elapsed_ms": None, "visits": None, "error": None}
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["status"] = response.status_code
    result["elapsed_ms"] = round(response.elapsed.total_seconds() * 1000, 1)
    try:
        result["visits"] = int(json.loads(response.text)["visits"])
    except (ValueError, KeyError, TypeError) as exc:
        result["error"] = f"Відповідь без коректного лічильника visits ({type(exc).__name__})"
    return result


def check_proxy_chain(url, timeout=5):
    """Ланцюг проксі -> app -> БД підтверджено, якщо обидва запити 200 і visits зріс."""
    first = probe(url, timeout)
    second = probe(url, timeout)

    def describe(number, r):
        if r["status"] is None:
            return f"запит {number}: помилка ({r['error']})"
        text = f"запит {number}: HTTP {r['status']}, {r['elapsed_ms']} мс, visits={r['visits']}"
        return text + (f" [{r['error']}]" if r["error"] else "")

    ok = (
        first["status"] == 200 and second["status"] == 200
        and first["error"] is None and second["error"] is None
        and second["visits"] > first["visits"]
    )
    details = f"{describe(1, first)}; {describe(2, second)}"
    if ok:
        details += f"; лічильник зріс на {second['visits'] - first['visits']}"
    return {"ok": ok, "requests": [first, second], "details": details}