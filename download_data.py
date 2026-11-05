"""下载固定版本的数据并验证原始文件；不执行清洗或修改原始字段。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)


def load_sources() -> dict:
    return json.loads((ROOT / "data_sources.json").read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_file(path: Path, specification: dict) -> None:
    """表头和摘要不符时拒绝文件，防止错误页面或残缺下载进入后续流程。"""
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError(f"文件缺失或为空：{path}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        columns = next(csv.reader(stream), [])
    if columns != specification["columns"]:
        raise ValueError(f"表头不符合固定版本：{path.name}，实际为 {columns}")
    expected = specification.get("sha256")
    if expected and sha256_file(path) != expected:
        raise ValueError(f"文件校验值不符：{path}；请使用 --force 重新下载")


def install_file(source: Path, destination: Path, specification: dict) -> None:
    """先复制到同一目录的临时文件，验证后再原子替换目标文件。"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as stream:
        temporary = Path(stream.name)
    try:
        shutil.copyfile(source, temporary)
        validate_file(temporary, specification)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def download_dataset(name: str, data_dir: Path, force: bool = False) -> list[Path]:
    specification = load_sources()[name]
    files = specification["files"]
    targets = [data_dir / item["destination"] for item in files.values()]
    if not force and all(path.is_file() for path in targets):
        for path, item in zip(targets, files.values(), strict=True):
            validate_file(path, item)
        LOGGER.info("%s：本地文件校验通过，跳过下载", name)
        return targets

    # 避免写入用户全局缓存，也不把数据重复下载到 Git 跟踪目录。
    os.environ.setdefault("KAGGLEHUB_CACHE", str(ROOT / ".cache" / "kagglehub"))
    import kagglehub

    LOGGER.info("开始下载 %s", specification["handle"])
    cache = Path(kagglehub.dataset_download(specification["handle"], force_download=force))
    for filename, item in files.items():
        # 固定版本的原始文件名保留在配置中，只规范本地目标文件名。
        source = cache / filename
        validate_file(source, item)
    for filename, item in files.items():
        install_file(cache / filename, data_dir / item["destination"], item)
    LOGGER.info("%s：%d 个文件下载及校验完成", name, len(files))
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["all", "retail", "olist"], default="all")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--force", action="store_true", help="重新下载固定版本并替换本地文件")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    failed = False
    names = list(load_sources()) if args.dataset == "all" else [args.dataset]
    for name in names:
        try:
            download_dataset(name, args.data_dir.resolve(), args.force)
        except Exception as exc:
            LOGGER.error("%s 下载失败：%s", name, exc)
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
