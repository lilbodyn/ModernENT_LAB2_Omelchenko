"""Збереження результатів: inventory.json та report.csv."""

import csv
import json


def save_inventory(path, cli, api):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"cli": cli, "api": api}, f, ensure_ascii=False, indent=2)
        f.write("\n")


def save_report(path, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["check", "result", "details"])
        writer.writerows(rows)