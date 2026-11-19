"""Збір даних через Docker CLI: Paramiko виконує команди по SSH, Python розбирає текстовий вивід."""

import re
import shlex

import paramiko

from config import SSHParams

CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{64}$")
# приклад рядка docker port: "80/tcp -> 0.0.0.0:8080" або "80/tcp -> [::]:8080"
PORT_LINE_RE = re.compile(
    r"^(?P<container_port>\d+)/(?P<proto>\w+) -> (?P<host_ip>.+):(?P<host_port>\d+)$"
)


class SSHConnectionError(Exception):
    """Вузол недоступний, відмова автентифікації або обрив зв'язку."""


class CommandError(Exception):
    """Віддалена команда завершилась з ненульовим кодом."""

    def __init__(self, command, exit_code, stderr):
        super().__init__(f"Команда завершилась з кодом {exit_code}: {command} | stderr: {stderr}")
        self.command = command
        self.exit_code = exit_code
        self.stderr = stderr


class ParseError(Exception):
    """Вивід команди має неочікуваний формат."""


# Розбір текстового виводу
def parse_ps_output(text):
    """'<ID> <Image> <State>' -> [{'id','image','state'}]"""
    containers = []
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 3 or not CONTAINER_ID_RE.match(parts[0]):
            raise ParseError(f"Неочікуваний рядок docker ps: {line!r}")
        containers.append({"id": parts[0], "image": parts[1], "state": parts[2]})
    return containers


def parse_service_line(text):
    """'<service> <StartedAt>' -> (service, started_at)"""
    parts = text.split()
    if len(parts) != 2:
        raise ParseError(f"Неочікуваний вивід docker inspect (сервіс/час): {text!r}")
    return parts[0], parts[1]


def parse_networks_output(text):
    """Рядки '<network> <ip>' -> [{'name','ip'}]. IP може бути порожнім (контейнер зупинено)."""
    networks = []
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        networks.append({"name": parts[0], "ip": parts[1] if len(parts) > 1 else ""})
    return networks


def parse_ports_output(text):
    """Рядки docker port -> [{'host_ip','host_port','container_port','proto'}]. Порожній вивід = немає портів."""
    ports = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = PORT_LINE_RE.match(line)
        if match is None:
            raise ParseError(f"Неочікуваний рядок docker port: {line!r}")
        ports.append(match.groupdict())
    return ports


# Клас-обгортка над Paramiko
class SSHCliCollector:
    def __init__(self, params: SSHParams, timeout: int = 10):
        self.params = params
        self.timeout = timeout
        self._client = None

    def connect(self):
        client = paramiko.SSHClient()
        client.load_system_host_keys() # відбитки з ~/.ssh/known_hosts
        client.set_missing_host_key_policy(paramiko.RejectPolicy()) # невідомий хост не приймаємо
        try:
            client.connect(
                hostname=self.params.hostname,
                port=self.params.port,
                username=self.params.username,
                key_filename=self.params.key_path,
                timeout=self.timeout,
                banner_timeout=self.timeout,
                auth_timeout=self.timeout,
                allow_agent=False,
                look_for_keys=False,
            )
        except (paramiko.SSHException, OSError) as exc:
            raise SSHConnectionError(
                f"Не вдалося підключитися до {self.params.hostname}:{self.params.port} "
                f"({type(exc).__name__}: {exc})"
            ) from exc
        self._client = client

    def close(self):
        if self._client is not None:
            self._client.close()
            self._client = None

    def run(self, command):
        """Виконує команду, повертає stdout. Код виходу != 0 -> CommandError."""
        if self._client is None:
            raise SSHConnectionError("SSH-сесію не відкрито")
        try:
            _, stdout, stderr = self._client.exec_command(command, timeout=self.timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            exit_code = stdout.channel.recv_exit_status()
        except (paramiko.SSHException, OSError) as exc:
            raise SSHConnectionError(f"Обрив зв'язку під час виконання команди: {exc}") from exc
        if exit_code != 0:
            raise CommandError(command, exit_code, err.strip())
        return out

    # Окремі команди з контрольного переліку завдання
    def hostname(self):
        return self.run("hostname").strip()

    def engine_version(self):
        return self.run("docker info --format '{{.ServerVersion}}'").strip()

    def list_project_containers(self, project):
        label_filter = shlex.quote(f"label=com.docker.compose.project={project}")
        command = (
            "docker ps -a --no-trunc --filter " + label_filter
            + " --format '{{.ID}} {{.Image}} {{.State}}'"
        )
        return parse_ps_output(self.run(command))

    @staticmethod
    def _checked_id(container_id):
        # захист: у shell-команду підставляємо лише повний hex-ID
        if not CONTAINER_ID_RE.match(container_id):
            raise ParseError(f"Некоректний ID контейнера: {container_id!r}")
        return container_id

    def inspect_service_and_start(self, container_id):
        cid = self._checked_id(container_id)
        command = (
            "docker inspect --format "
            "'{{index .Config.Labels \"com.docker.compose.service\"}} {{.State.StartedAt}}' " + cid
        )
        return parse_service_line(self.run(command))

    def inspect_networks(self, container_id):
        cid = self._checked_id(container_id)
        command = (
            "docker inspect --format "
            "'{{range $name, $network := .NetworkSettings.Networks}}"
            "{{println $name $network.IPAddress}}{{end}}' " + cid
        )
        return parse_networks_output(self.run(command))

    def container_ports(self, container_id):
        cid = self._checked_id(container_id)
        return parse_ports_output(self.run("docker port " + cid))

    def collect(self, project):
        """Повний збір: сирі (ще не нормалізовані) дані по всіх контейнерах проєкту."""
        raw = {"hostname": self.hostname(), "containers": []}
        for item in self.list_project_containers(project):
            service, started_at = self.inspect_service_and_start(item["id"])
            raw["containers"].append({
                **item,
                "service": service,
                "started_at": started_at,
                "networks": self.inspect_networks(item["id"]),
                "ports": self.container_ports(item["id"]),
            })
        return raw