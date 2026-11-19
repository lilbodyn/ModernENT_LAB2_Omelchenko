"""Порівняння нормалізованих знімків CLI та API. Контейнери зіставляються за повним ID."""

SCALAR_FIELDS = ("service", "image", "state", "started_at")


def compare_snapshots(cli, api):
    """Повертає список відмінностей [(scope, повідомлення)]. Порожній список = знімки збігаються."""
    diffs = []

    for key in ("hostname", "compose_project"):
        if cli[key] != api[key]:
            diffs.append(("snapshot", f"{key}: CLI={cli[key]!r}, API={api[key]!r}"))

    cli_map = {c["id"]: c for c in cli["containers"]}
    api_map = {c["id"]: c for c in api["containers"]}

    for cid in sorted(cli_map.keys() - api_map.keys()):
        c = cli_map[cid]
        diffs.append((c["service"], f"контейнер {cid[:12]} є лише в CLI"))
    for cid in sorted(api_map.keys() - cli_map.keys()):
        c = api_map[cid]
        diffs.append((c["service"], f"контейнер {cid[:12]} є лише в API"))

    for cid in sorted(cli_map.keys() & api_map.keys()):
        a, b = cli_map[cid], api_map[cid]
        scope = a["service"]
        for field in SCALAR_FIELDS:
            if a[field] != b[field]:
                diffs.append((scope, f"{field}: CLI={a[field]!r}, API={b[field]!r}"))
        if a["networks"] != b["networks"]:
            diffs.append((scope, f"networks: CLI={a['networks']}, API={b['networks']}"))
        if set(a["ports"]) != set(b["ports"]):
            diffs.append((scope, f"ports: CLI={sorted(a['ports'])}, API={sorted(b['ports'])}"))
    return diffs