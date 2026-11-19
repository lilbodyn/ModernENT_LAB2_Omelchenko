"""Перевірка мережевої конфігурації: таблиця "мережа -> контейнери" та політика публікації портів."""

def build_network_table(snapshot):
    """{'мережа': [{'service','ip'}, ...]} за полем networks (NetworkSettings.Networks)."""
    table = {}
    for container in snapshot["containers"]:
        for network, ip in container["networks"].items():
            table.setdefault(network, []).append({"service": container["service"], "ip": ip})
    return {
        network: sorted(members, key=lambda m: m["service"])
        for network, members in sorted(table.items())
    }


def format_network_table(table):
    lines = []
    for network, members in table.items():
        lines.append(f"Мережа: {network}")
        for member in members:
            lines.append(f"  - {member['service']:<8} {member['ip']}")
    return "\n".join(lines)


def check_port_publishing(snapshot, proxy_service):
    """Повертає список порушень. Порожній список = "відповідає вимогам"."""
    violations = []
    services = [c["service"] for c in snapshot["containers"]]
    if proxy_service not in services:
        violations.append(f"У проєкті немає контейнера веб-проксі '{proxy_service}'")
    for container in snapshot["containers"]:
        service, ports = container["service"], container["ports"]
        if service == proxy_service:
            if not ports:
                violations.append(f"Контейнер сервісу '{service}' (веб-проксі) не публікує жодного порту")
        elif ports:
            violations.append(
                f"Контейнер сервісу '{service}' має опубліковані порти: {', '.join(ports)}"
            )
    return violations