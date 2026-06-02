import yaml
import sys
from datetime import datetime


def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(level: str, msg: str):
    print(f"[{now_str()}] [{level}] {msg}")
