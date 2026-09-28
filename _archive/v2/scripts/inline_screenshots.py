#!/usr/bin/env python3
"""将 creative-showcase.html 中的截图引用替换为 base64 内联，生成自包含 HTML 文件。"""

import base64
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent / "frontend"
INPUT_HTML = BASE_DIR / "creative-showcase.html"
OUTPUT_HTML = BASE_DIR / "creative-showcase-standalone.html"
SCREENSHOTS_DIR = BASE_DIR / "screenshots"

# PNG MIME type
MIME = "image/png"


def img_to_base64(img_path: Path) -> str:
    """读取图片文件并返回 base64 编码的 data URI。"""
    data = img_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{MIME};base64,{b64}"


def main():
    html = INPUT_HTML.read_text(encoding="utf-8")

    # 匹配 src="screenshots/xxx.png" 的引用
    pattern = re.compile(r'src="screenshots/([^"]+\.(?:png|jpg|jpeg|gif|svg))"', re.IGNORECASE)

    replaced = 0
    not_found = []

    def replace_match(match):
        nonlocal replaced, not_found
        filename = match.group(1)
        img_path = SCREENSHOTS_DIR / filename
        if img_path.exists():
            data_uri = img_to_base64(img_path)
            replaced += 1
            return f'src="{data_uri}"'
        else:
            not_found.append(filename)
            return match.group(0)

    result = re.sub(pattern, replace_match, html)

    OUTPUT_HTML.write_text(result, encoding="utf-8")

    print(f"输入文件: {INPUT_HTML}")
    print(f"输出文件: {OUTPUT_HTML}")
    print(f"替换图片数: {replaced}")
    if not_found:
        print(f"未找到的图片: {not_found}")
    print(f"输出文件大小: {OUTPUT_HTML.stat().st_size / 1024 / 1024:.2f} MB")


if __name__ == "__main__":
    main()
