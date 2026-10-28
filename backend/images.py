"""读取与验证真实图片，并保留可追溯的原始字节。"""
import io
import shutil
import warnings
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .settings import EXTENSIONS, LIMITS


class InputError(ValueError):
    pass


def check_space(directory):
    if shutil.disk_usage(directory).free < LIMITS["min_free_bytes"]:
        raise InputError("可用磁盘空间不足 1 GiB，请先离线归档运行数据")


def decode(data):
    if not data or len(data) > LIMITS["max_file_bytes"]:
        raise InputError("图片为空或超过 20 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in {"JPEG", "PNG", "BMP"}:
                    raise InputError("仅支持 JPEG、PNG、BMP 图片内容")
                if image.width * image.height > LIMITS["max_pixels"]:
                    raise InputError("图片超过 4000 万像素")
                image.verify()
        result = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if result is None:
            raise InputError("图片解码失败")
        return result
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InputError(f"无效图片：{exc}") from exc


def inventory(directory):
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise InputError("配置的图片目录不存在")
    files = []
    for path in directory.iterdir():
        if path.suffix.lower() not in EXTENSIONS or not path.is_file():
            continue
        if path.resolve().parent != directory:
            raise InputError("数据目录不允许指向外部的图片符号链接")
        stat = path.stat()
        files.append({"path": path, "size": stat.st_size, "mtime": stat.st_mtime_ns})
        if len(files) > LIMITS["max_images"]:
            raise InputError("目录图片超过单任务 10000 张限制，请分批运行")
    return sorted(files, key=lambda item: (item["path"].name.casefold(), item["path"].name))

