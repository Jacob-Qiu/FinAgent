"""Storage helpers for extension-layer data assets."""

from __future__ import annotations

from pathlib import Path


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_parquet(path: Path):
    import pandas as pd

    return pd.read_parquet(path)


def write_parquet(frame, path: Path) -> None:
    ensure_directory(path.parent)
    try:
        frame.to_parquet(path, index=False)
    except ImportError as exc:
        raise RuntimeError(
            "Writing Parquet requires `pyarrow` or `fastparquet`. "
            "Install one of them in the runtime environment before running the pipeline."
        ) from exc
