"""Демонстрація обробки помилок: успіх, помилка команди, недоступний вузол."""

from dataclasses import replace

from config import resolve_ssh_params
from ssh_cli_collector import CommandError, SSHCliCollector, SSHConnectionError

ALIAS = "lab2-vm"
params = resolve_ssh_params(ALIAS)

print("--- Сценарій 1: успішна команда ---")
collector = SSHCliCollector(params, timeout=5)
collector.connect()
print("hostname:", collector.hostname())

print("\n--- Сценарій 2: помилка команди (неіснуючий контейнер) ---")
try:
    collector.inspect_service_and_start("0" * 64)
except CommandError as exc:
    print(f"CommandError: код виходу {exc.exit_code}; stderr: {exc.stderr}")
finally:
    collector.close()

print("\n--- Сценарій 3: недоступний вузол (SSH-порт 2299 не слухає) ---")
try:
    SSHCliCollector(replace(params, port=2299), timeout=3).connect()
except SSHConnectionError as exc:
    print(f"SSHConnectionError: {exc}")