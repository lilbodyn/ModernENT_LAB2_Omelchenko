"""Конфігурація запуску: аргументи командного рядка та SSH-параметри."""

import argparse
import getpass
import os
from dataclasses import dataclass
from pathlib import Path

import paramiko

DEFAULT_SSH_ALIAS = "lab2-vm"
DEFAULT_PROJECT = "lab1"
DEFAULT_PROXY_URL = "http://127.0.0.1:8080/"
PROXY_SERVICE = "proxy"


class ConfigError(Exception):
    """Помилка конфігурації (немає ~/.ssh/config, ключа тощо)."""


@dataclass(frozen=True)
class SSHParams:
    alias: str
    hostname: str
    port: int
    username: str
    key_path: str


def resolve_ssh_params(alias: str) -> SSHParams:
    """Читає ~/.ssh/config і повертає параметри підключення для псевдоніма."""
    config_path = Path.home() / ".ssh" / "config"
    if not config_path.is_file():
        raise ConfigError(f"Не знайдено файл {config_path}")

    entry = paramiko.SSHConfig.from_path(str(config_path)).lookup(alias)

    key_files = entry.get("identityfile", [])
    if not key_files:
        raise ConfigError(f"Для хоста '{alias}' у ~/.ssh/config не вказано IdentityFile")
    key_path = os.path.expanduser(key_files[0])
    if not os.path.isfile(key_path):
        raise ConfigError(f"Файл ключа не знайдено: {key_path}")

    return SSHParams(
        alias=alias,
        hostname=entry.get("hostname", alias),
        port=int(entry.get("port", 22)),
        username=entry.get("user", getpass.getuser()),
        key_path=key_path,
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Інвентаризація та перевірка контейнерної мережі (ЛР2): "
        "Docker CLI + Docker Engine API через SSH."
    )
    parser.add_argument("--ssh-host", default=DEFAULT_SSH_ALIAS,
                        help="псевдонім хоста з ~/.ssh/config (за замовчуванням: %(default)s)")
    parser.add_argument("--project", default=DEFAULT_PROJECT,
                        help="назва Compose-проєкту (за замовчуванням: %(default)s)")
    parser.add_argument("--proxy-url", default=DEFAULT_PROXY_URL,
                        help="URL веб-проксі (за замовчуванням: %(default)s)")
    parser.add_argument("--output-dir", default="output",
                        help="каталог для inventory.json та report.csv")
    parser.add_argument("--timeout", type=int, default=10,
                        help="тайм-аут SSH/Docker, с (за замовчуванням: %(default)s)")
    parser.add_argument("--http-timeout", type=int, default=5,
                        help="тайм-аут HTTP-запитів, с (за замовчуванням: %(default)s)")
    parser.add_argument("--sdk-use-ssh-client", action="store_true",
                        help="Docker SDK через системний ssh.exe замість Paramiko (запасний варіант)")
    return parser.parse_args(argv)