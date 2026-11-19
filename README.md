# ЛР2 - Автоматизація мережевих задач. Інвентаризація та перевірка контейнерної мережі засобами Python через Docker CLI та Docker Engine API.


Скрипт збирає дані про контейнери проєкту з ЛР1 (db, app, proxy) через SSH двома способами
(Docker CLI і Docker Engine API), порівнює їх, перевіряє мережу та роботу веб-проксі.
Результати пише у `output/inventory.json` і `output/report.csv`.

## Що має бути налаштовано

- Windows з Python 3.14, VM Ubuntu у VirtualBox (NAT) з Docker
- проєкт ЛР1 у `~/lab1` на VM, запущений (`docker compose up -d`)
- у VirtualBox проброс портів: `127.0.0.1:2222 -> 22` і `127.0.0.1:8080 -> 8080`
- SSH-ключ `~/.ssh/lab2_ed25519` додано на VM, у `~/.ssh/config` є запис:

```
Host lab2-vm
    HostName 127.0.0.1
    Port 2222
    User omelchenko
    IdentityFile ~/.ssh/lab2_ed25519
```

## Запуск

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Перевірка помилок (успіх, помилка команди, недоступний вузол):

```
python demo_errors.py
```

## Моніторинг (додаткове завдання)

```
python monitor.py --interval 10
```

Кожні 10 секунд перевіряє стани db/app/proxy через Docker SDK та HTTP-статус проксі,
дописує рядок у `output/monitoring.csv`. Зупинка - Ctrl+C. Параметр `--count N` задає
кількість перевірок.

## Файли

- `main.py` - запуск усіх перевірок
- `config.py` - параметри і SSH-налаштування
- `ssh_cli_collector.py` - збір через Docker CLI (Paramiko)
- `api_collector.py` - збір через Docker SDK
- `normalizer.py` - приведення даних до одного формату
- `network_check.py` - таблиця мереж і перевірка портів
- `http_check.py` - запити через проксі
- `compare.py` - порівняння CLI та API
- `report.py` - запис json і csv
- `demo_errors.py` - демонстрація помилок
- `monitor.py` - моніторинг (додаткове завдання)

Код завершення `main.py`: 0 - все добре, 1 - є невдалі перевірки, 2 - немає SSH-доступу.