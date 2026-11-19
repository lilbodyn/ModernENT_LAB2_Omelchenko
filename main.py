"""Інвентаризація та перевірка контейнерної мережі проєкту ЛР1 (Docker CLI + Docker Engine API через SSH)."""

from pathlib import Path

from api_collector import ApiError, collect_api
from compare import compare_snapshots
from config import PROXY_SERVICE, ConfigError, parse_args, resolve_ssh_params
from http_check import check_proxy_chain
from network_check import build_network_table, check_port_publishing, format_network_table
from normalizer import normalize_api, normalize_cli
from report import save_inventory, save_report
from ssh_cli_collector import CommandError, ParseError, SSHCliCollector, SSHConnectionError

CLI_ERRORS = (SSHConnectionError, CommandError, ParseError)


def title(text):
    print(f"\n=== {text} ===")


def gather_cli(collector, project):
    return normalize_cli(collector.collect(project), project)


def gather_api(args, params):
    raw = collect_api(params, args.project, args.timeout, args.sdk_use_ssh_client)
    return normalize_api(raw, args.project)


def describe_snapshot(snapshot):
    print(f"Хост: {snapshot['hostname']}; проєкт: {snapshot['compose_project']}; "
          f"час збору: {snapshot['collected_at']}")
    for c in snapshot["containers"]:
        print(f"  {c['service']:<6} {c['id'][:12]}  {c['image']:<18} {c['state']:<8} "
              f"мережі={c['networks']} порти={c['ports']}")


def main():
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = [] # (перевірка, результат, деталі) -> report.csv

    # 1. SSH-доступ і Docker Engine
    title("1. SSH-доступ та Docker Engine")
    collector = None
    try:
        params = resolve_ssh_params(args.ssh_host)
        collector = SSHCliCollector(params, args.timeout)
        collector.connect()
        engine_version = collector.engine_version()
    except (ConfigError, SSHConnectionError, CommandError) as exc:
        print(f"ПОМИЛКА: {exc}")
        rows.append(("ssh_docker_access", "FAIL", str(exc).replace("\n", " ")))
        save_report(out_dir / "report.csv", rows)
        return 2
    details = f"{params.username}@{params.hostname}:{params.port}; Docker Engine {engine_version}"
    print(f"OK: {details}")
    rows.append(("ssh_docker_access", "PASS", details))

    try:
        # 2. Збір через Docker CLI
        title("2. Збір через Docker CLI (Paramiko)")
        cli = None
        try:
            cli = gather_cli(collector, args.project)
            describe_snapshot(cli)
            rows.append(("cli_inventory", "PASS", f"контейнерів: {len(cli['containers'])}"))
        except CLI_ERRORS as exc:
            print(f"ПОМИЛКА: {exc}")
            rows.append(("cli_inventory", "FAIL", str(exc).replace("\n", " ")))

        # 3. Збір через Docker Engine API
        title("3. Збір через Docker Engine API (Docker SDK)")
        api = None
        try:
            api = gather_api(args, params)
            describe_snapshot(api)
            rows.append(("api_inventory", "PASS", f"контейнерів: {len(api['containers'])}"))
        except ApiError as exc:
            print(f"ПОМИЛКА: {exc}")
            rows.append(("api_inventory", "FAIL", str(exc).replace("\n", " ")))

        # 4. Мережева конфігурація
        title("4. Мережева конфігурація")
        base = api or cli
        if base is None:
            rows.append(("network_policy", "FAIL", "немає даних інвентаризації"))
            print("ПРОПУЩЕНО: немає даних інвентаризації")
        else:
            table = build_network_table(base)
            print(format_network_table(table))
            for network, members in table.items():
                rows.append((f"network_table:{network}", "INFO",
                             "; ".join(f"{m['service']}={m['ip']}" for m in members)))
            violations = check_port_publishing(base, PROXY_SERVICE)
            if violations:
                print("ПОРУШЕННЯ:")
                for v in violations:
                    print(f"  - {v}")
                rows.append(("network_policy", "FAIL", " | ".join(violations)))
            else:
                print("Результат: відповідає вимогам")
                rows.append(("network_policy", "PASS", "відповідає вимогам: порт на хості лише у веб-проксі"))

        # 5. HTTP-перевірка
        title("5. HTTP-перевірка через веб-проксі")
        http = check_proxy_chain(args.proxy_url, args.http_timeout)
        print(http["details"])
        print("Результат:", "ланцюг проксі -> app -> БД працює" if http["ok"] else "перевірка не пройдена")
        rows.append(("http_chain", "PASS" if http["ok"] else "FAIL", http["details"]))

        # 6. Порівняння CLI та API
        title("6. Порівняння CLI та API")
        if cli is None or api is None:
            print("ПРОПУЩЕНО: потрібні обидва знімки")
            rows.append(("cli_api_compare", "FAIL", "один зі знімків не зібрано"))
        else:
            diffs = compare_snapshots(cli, api)
            first_run_diffs = diffs
            if diffs:
                print("Виявлено відмінності:")
                for scope, message in diffs:
                    print(f"  - [{scope}] {message}")
                print("Повторне опитування для перевірки причини...")
                try:
                    cli2, api2 = gather_cli(collector, args.project), gather_api(args, params)
                except (*CLI_ERRORS, ApiError) as exc:
                    print(f"ПОМИЛКА повторного опитування: {exc}")
                    final_diffs, verdict = diffs, ("FAIL", f"повторне опитування не вдалося: {exc}")
                else:
                    cli, api = cli2, api2
                    final_diffs = compare_snapshots(cli, api)
                    if final_diffs:
                        verdict = ("FAIL", "відмінності збереглися при повторі: імовірна помилка обробки")
                    else:
                        verdict = ("WARN", "відмінності зникли при повторі: зміна стану між опитуваннями")
            else:
                final_diffs, verdict = [], ("PASS", "знімки CLI та API збігаються")

            print("Результат:", verdict[1])
            rows.append(("cli_api_compare", verdict[0], verdict[1]))
            scopes = {c["service"] for c in api["containers"]} | {c["service"] for c in cli["containers"]}
            for service in sorted(scopes):
                mine = [m for s, m in final_diffs if s == service]
                rows.append((f"compare:{service}", "FAIL" if mine else "PASS",
                             " | ".join(mine) if mine else "склад, стан, мережі та порти збігаються"))
            if any(s == "snapshot" for s, _ in final_diffs):
                rows.append(("compare:snapshot", "FAIL",
                             " | ".join(m for s, m in final_diffs if s == "snapshot")))

        # 7. Збереження
        title("7. Збереження результатів")
        save_inventory(out_dir / "inventory.json", cli, api)
        save_report(out_dir / "report.csv", rows)
        print(f"Збережено: {out_dir / 'inventory.json'}, {out_dir / 'report.csv'}")
    finally:
        collector.close()

    return 1 if any(result == "FAIL" for _, result, _ in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())