#!/usr/bin/env python3
"""初始化数据库 - 创建表结构"""

import sys
from pathlib import Path

# 确保项目根目录在 path 中
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from src.database import init_db, get_engine
import yaml


def main():
    config_path = root / "config.yaml"
    db_url = None
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        url = cfg.get("database", {}).get("url", "")
        if url and "sqlite" in url:
            if "sqlite:///" in url:
                rel = url.replace("sqlite:///", "")
                if not Path(rel).is_absolute():
                    abs_path = (root / rel).resolve()
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    db_url = f"sqlite:///{abs_path}"
                else:
                    db_url = url
            else:
                db_url = url

    engine = get_engine(db_url)
    init_db(engine)
    print("数据库初始化完成")


if __name__ == "__main__":
    main()
