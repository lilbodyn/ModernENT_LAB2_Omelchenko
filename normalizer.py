"""Приведення результатів CLI та API до спільної нормалізованої структури."""

import re
from datetime import datetime, timezone

TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d+))?Z$")


def utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_timestamp(value):
    """Docker віддає наносекунди (9 цифр) - зводимо до мікросекунд (6 цифр)."""
    match = TIMESTAMP_RE.match(value.strip())
    if match is None:
        raise ValueError(f"Невідомий формат часу: {value!r}")
    fraction = (match.group(2) or "").ljust(6, "0")[:6]
    return f"{match.group(1)}.{fraction}Z"


def _snapshot(source, hostname, project, containers):
    return {
        "source": source,
        "hostname": hostname,
        "compose_project": project,
        "collected_at": utc_now_iso(),
        "containers": sorted(containers, key=lambda c: (c["service"], c["id"])),
    }


def normalize_cli(raw, project):
    containers = []
    for item in raw["containers"]:
        containers.append({
            "service": item["service"],
            "id": item["id"],
            "image": item["image"],
            "state": item["state"],
            "started_at": normalize_timestamp(item["started_at"]),
            "networks": {n["name"]: n["ip"] for n in sorted(item["networks"], key=lambda n: n["name"])},
            "ports": sorted({
                f"{p['host_port']}->{p['container_port']}/{p['proto']}" for p in item["ports"]
            }),
        })
    return _snapshot("cli", raw["hostname"], project, containers)


def normalize_api(raw, project):
    containers = []
    for item in raw["containers"]:
        attrs = item["attrs"]
        net_settings = attrs["NetworkSettings"]
        networks = {
            name: data.get("IPAddress", "")
            for name, data in sorted(net_settings["Networks"].items())
        }
        ports = set()
        # Ports: {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}, ...]} або {"8000/tcp": None}
        for container_port, bindings in (net_settings.get("Ports") or {}).items():
            for binding in bindings or []: # None = порт оголошено, але не опубліковано
                ports.add(f"{binding['HostPort']}->{container_port}")
        containers.append({
            "service": item["labels"]["com.docker.compose.service"],
            "id": item["id"],
            "image": attrs["Config"]["Image"],
            "state": attrs["State"]["Status"],
            "started_at": normalize_timestamp(attrs["State"]["StartedAt"]),
            "networks": networks,
            "ports": sorted(ports),
        })
    return _snapshot("api", raw["hostname"], project, containers)