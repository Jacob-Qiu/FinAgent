"""
创建日期：2026年02月11日
介绍： 配置加载器
"""
import yaml
from pathlib import Path

def load_config(path: str = "config.yml"):
    with open(Path(path), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
