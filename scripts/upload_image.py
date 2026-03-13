#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "Pillow>=10.0",
#     "pillow-heif>=0.18.0",
# ]
# ///
"""画像を AVIF に変換して Cloudflare R2 にアップロードし、公開 URL を返す。

Usage:
    uv run scripts/upload_image.py image1.png image2.jpg
    uv run scripts/upload_image.py --quality 70 screenshot.png
    uv run scripts/upload_image.py --repo owner/repo --number 123 result.png
"""

import argparse
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pillow_heif import register_heif_opener

register_heif_opener()

from PIL import Image  # noqa: E402

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
ENV_FILE = PROJECT_DIR / ".env"


def load_env() -> dict[str, str]:
    """Load .env file from project root."""
    env = {}
    if not ENV_FILE.exists():
        return env
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip("\"'")
    return env


class Config:
    """Configuration loaded from .env with CLI overrides."""

    def __init__(self, args: argparse.Namespace, env: dict[str, str]) -> None:
        self.bucket = args.bucket or env.get("R2_BUCKET", "")
        self.base_url = args.base_url or env.get("R2_PUBLIC_BASE_URL", "")
        self.quality = args.quality or int(env.get("AVIF_QUALITY", "80"))
        self.max_file_bytes = int(env.get("MAX_FILE_BYTES", str(10 * 1024 * 1024)))
        self.max_width = int(env.get("MAX_WIDTH", "0"))  # 0 = no resize
        self.max_height = int(env.get("MAX_HEIGHT", "0"))  # 0 = no resize
        self.allowed_ext = set(
            env.get("ALLOWED_EXTENSIONS", ".png,.jpg,.jpeg,.webp,.gif").split(",")
        )

    def validate(self) -> None:
        if not self.bucket:
            print("Error: R2_BUCKET not set. Use --bucket or set in .env", file=sys.stderr)
            sys.exit(1)
        if not self.base_url:
            print("Error: R2_PUBLIC_BASE_URL not set. Use --base-url or set in .env", file=sys.stderr)
            sys.exit(1)


def convert_to_avif(input_path: Path, config: Config) -> Path:
    """Convert image to AVIF format with optional resize."""
    img = Image.open(input_path)

    # Resize if max dimensions are set
    if config.max_width or config.max_height:
        max_w = config.max_width or img.width
        max_h = config.max_height or img.height
        if img.width > max_w or img.height > max_h:
            img.thumbnail((max_w, max_h), Image.LANCZOS)

    if img.mode in ("RGBA", "LA", "PA"):
        pass  # keep alpha
    elif img.mode != "RGB":
        img = img.convert("RGB")

    output_path = Path(tempfile.gettempdir()) / f"{uuid.uuid4().hex[:8]}.avif"
    img.save(output_path, format="AVIF", quality=config.quality)
    return output_path


def generate_key(
    filename: str,
    repo: str | None = None,
    number: int | None = None,
) -> str:
    """Generate R2 object key."""
    now = datetime.now(timezone.utc)
    uid = uuid.uuid4().hex[:12]
    stem = Path(filename).stem
    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in stem)

    if repo and number:
        return f"github/{repo}/{number}/{now:%Y/%m}/{uid}-{safe_name}.avif"
    return f"uploads/{now:%Y/%m}/{uid}-{safe_name}.avif"


def upload_to_r2(
    file_path: Path,
    bucket: str,
    key: str,
) -> None:
    """Upload file to R2 using wrangler CLI."""
    cmd = [
        "bunx",
        "wrangler",
        "r2",
        "object",
        "put",
        f"{bucket}/{key}",
        "--file",
        str(file_path),
        "--content-type",
        "image/avif",
        "--remote",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: wrangler upload failed\n{result.stderr}", file=sys.stderr)
        sys.exit(1)


def validate_file(path: Path, config: Config) -> None:
    """Validate input file."""
    if not path.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)
    if path.suffix.lower() not in config.allowed_ext:
        print(
            f"Error: {path.suffix} is not supported. Use: {', '.join(sorted(config.allowed_ext))}",
            file=sys.stderr,
        )
        sys.exit(1)
    if path.stat().st_size > config.max_file_bytes:
        limit_mb = config.max_file_bytes / 1024 / 1024
        print(f"Error: {path} exceeds {limit_mb:.0f}MB limit", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload images to R2 as AVIF")
    parser.add_argument("files", nargs="+", help="Image files to upload")
    parser.add_argument("--quality", type=int, default=0, help="AVIF quality 1-100 (default: .env or 80)")
    parser.add_argument("--repo", help="GitHub repo (owner/repo)")
    parser.add_argument("--number", type=int, help="Issue/PR number")
    parser.add_argument("--bucket", help="R2 bucket name (override .env)")
    parser.add_argument("--base-url", help="Public base URL (override .env)")
    parser.add_argument("--format", choices=["url", "markdown", "json"], default="url", help="Output format")
    args = parser.parse_args()

    env = load_env()
    config = Config(args, env)
    config.validate()

    results = []

    for file_str in args.files:
        file_path = Path(file_str).resolve()
        validate_file(file_path, config)

        avif_path = convert_to_avif(file_path, config)
        original_size = file_path.stat().st_size
        avif_size = avif_path.stat().st_size

        key = generate_key(file_path.name, args.repo, args.number)
        upload_to_r2(avif_path, config.bucket, key)

        url = f"{config.base_url.rstrip('/')}/{key}"

        results.append({
            "url": url,
            "original": file_path.name,
            "original_size": original_size,
            "avif_size": avif_size,
            "key": key,
            "markdown": f"![{file_path.stem}]({url})",
        })

        avif_path.unlink(missing_ok=True)

    # Output
    for r in results:
        if args.format == "url":
            print(r["url"])
        elif args.format == "markdown":
            print(r["markdown"])
        elif args.format == "json":
            import json
            print(json.dumps(r, ensure_ascii=False))


if __name__ == "__main__":
    main()
