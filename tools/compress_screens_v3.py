"""Compress v2 PNG screenshots into screens/v3/ (target ≤1.5 MiB total).

Pipeline per file:
  1. pngquant --quality=99-100 --nofs  (skip if quality cannot be met)
  2. oxipng -o max --strip safe        (lossless re-pack)
JPEG copies are taken from v2 unchanged.
"""

import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_PNG = os.path.join(ROOT, "screens", "v2", "png")
SRC_JPEG = os.path.join(ROOT, "screens", "v2", "jpeg")
DST_PNG = os.path.join(ROOT, "screens", "v3", "png")
DST_JPEG = os.path.join(ROOT, "screens", "v3", "jpeg")


def compress_png(src: str, dst: str) -> tuple[int, int, bool]:
    """Return (src_bytes, dst_bytes, quantized)."""
    shutil.copy2(src, dst)
    r = subprocess.run(
        ["pngquant", "--quality=99-100", "--nofs", "--force", "--output", dst, dst],
        capture_output=True,
    )
    quantized = r.returncode == 0
    subprocess.run(
        ["oxipng", "-o", "max", "--strip", "safe", dst],
        check=True,
        capture_output=True,
    )
    return os.path.getsize(src), os.path.getsize(dst), quantized


def main() -> int:
    os.makedirs(DST_PNG, exist_ok=True)
    os.makedirs(DST_JPEG, exist_ok=True)

    src_total = dst_total = 0
    quantized_count = 0

    for src in sorted(glob.glob(os.path.join(SRC_PNG, "*.png"))):
        name = os.path.basename(src)
        dst = os.path.join(DST_PNG, name)
        before, after, q = compress_png(src, dst)
        src_total += before
        dst_total += after
        if q:
            quantized_count += 1
        print(f"  {name}: {before // 1024}K → {after // 1024}K{'  [palette]' if q else ''}")

    for src in sorted(glob.glob(os.path.join(SRC_JPEG, "*.jpeg"))):
        shutil.copy2(src, os.path.join(DST_JPEG, os.path.basename(src)))

    print(
        f"\nPNG: {src_total / 1024 / 1024:.2f} MiB → {dst_total / 1024 / 1024:.2f} MiB "
        f"({quantized_count}/{len(glob.glob(os.path.join(SRC_PNG, '*.png')))} palette-compressed)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
