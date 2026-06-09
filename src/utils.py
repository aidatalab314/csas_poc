import os
import yaml
import sys
from datetime import datetime


def _deep_merge(base: dict, override: dict) -> dict:
    """遞迴合併：override 的 key 覆蓋 base，dict 值遞迴處理，其餘直接覆蓋。"""
    result = base.copy()
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def load_yaml(path: str) -> dict:
    """載入 YAML，若同目錄存在 .local.yaml 則自動合併（local 優先）。"""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    local_path = path.replace(".yaml", ".local.yaml")
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            local = yaml.safe_load(f) or {}
        data = _deep_merge(data, local)
        print(f"[load_yaml] 已載入本機覆蓋設定：{local_path}")

    return data


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(level: str, msg: str):
    print(f"[{now_str()}] [{level}] {msg}")
