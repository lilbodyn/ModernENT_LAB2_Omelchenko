"""Збір даних через Docker Engine API (Docker SDK for Python) з підключенням по SSH."""

import docker
import paramiko
import requests
from docker.errors import DockerException

from config import SSHParams


class ApiError(Exception):
    """Docker Engine API недоступний або повернув помилку."""


def collect_api(params: SSHParams, project, timeout=10, use_ssh_client=False):
    """Повертає сирі дані: ім'я хоста та attrs усіх контейнерів Compose-проєкту."""
    try:
        client = docker.DockerClient(
            base_url=f"ssh://{params.alias}:{params.port}",
            timeout=timeout,
            version="auto",
            use_ssh_client=use_ssh_client,
        )
        try:
            hostname = client.info()["Name"]
            engine_version = client.version()["Version"]
            containers = client.containers.list(
                all=True,
                filters={"label": f"com.docker.compose.project={project}"},
            )
            return {
                "hostname": hostname,
                "engine_version": engine_version,
                "containers": [
                    {"id": c.id, "labels": c.labels, "attrs": c.attrs} for c in containers
                ],
            }
        finally:
            client.close()
    except (DockerException, requests.RequestException, paramiko.SSHException, OSError) as exc:
        raise ApiError(f"Docker Engine API недоступний ({type(exc).__name__}: {exc})") from exc