"""Додаткове завдання: періодичний моніторинг проєкту ЛР1."""

import argparse
import csv
import time
from pathlib import Path

from api_collector import ApiError, collect_api
from config import (DEFAULT_PROJECT, DEFAULT_PROXY_URL, DEFAULT_SSH_ALIAS,
                    ConfigError, resolve_ssh_params)
from http_check import probe
from normalizer import utc_now_iso

SERVICES = ("db", "app", "proxy")


def parse_args():
    parser = argparse.ArgumentParser(description="Періодичний моніторинг проєкту ЛР1")
    parser.add_argument("--interval", type=int, default=10,
                        help="інтервал опитування, с (за замовчуванням: %(default)s)")
    parser.add_argument("--count", type=int, default=0,
                        help="кількість перевірок, 0 = працювати до Ctrl+C")
    parser.add_argument("--output", default="output/monitoring.csv")
    parser.add_argument("--ssh-host", default=DEFAULT_SSH_ALIAS)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--proxy-url", default=DEFAULT_PROXY_URL)
    parser.add_argument("--timeout", type=int, default=10, help="тайм-аут SSH/Docker, с")
    parser.add_argument("--http-timeout", type=int, default=5, help="тайм-аут HTTP, с")
    parser.add_argument("--sdk-use-ssh-client", action="store_true")
    return parser.parse_args()


def get_states(args, params):
    """{сервіс: стан} через Docker SDK. Якщо API недоступний - повертає None."""
    try:
        raw = collect_api(params, args.project, args.timeout, args.sdk_use_ssh_client)
    except ApiError:
        return None
    return {
        item["labels"]["com.docker.compose.service"]: item["attrs"]["State"]["Status"]
        for item in raw["containers"]
    }


def check_once(args, params):
    checked_at = utc_now_iso() # час початку перевірки, щоб рядки йшли рівно через interval
    states = get_states(args, params)
    http = probe(args.proxy_url, args.http_timeout)

    row = [checked_at]
    for service in SERVICES:
        if states is None:
            row.append("unknown") # не вдалося опитати Docker
        else:
            row.append(states.get(service, "missing")) # контейнера немає
    row.append(http["status"] if http["status"] is not None else "no_response")
    return row


def main():
    args = parse_args()
    try:
        params = resolve_ssh_params(args.ssh_host)
    except ConfigError as exc:
        print(f"ПОМИЛКА: {exc}")
        return 2

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Моніторинг кожні {args.interval} с, результат: {out_path}.")

    done = 0
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", *SERVICES, "http_status"])
        try:
            while True:
                started = time.monotonic()
                row = check_once(args, params)
                writer.writerow(row)
                f.flush()
                print("  ".join(str(x) for x in row))

                done += 1
                if args.count and done >= args.count:
                    break
                time.sleep(max(0, args.interval - (time.monotonic() - started)))
        except KeyboardInterrupt:
            print(f"\nЗупинено. Виконано перевірок: {done}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())