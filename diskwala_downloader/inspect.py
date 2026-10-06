"""Safe metadata diagnostic: python -m diskwala_downloader.inspect URL."""
import argparse

from .cli import inspect_url


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect a public DiskWala share")
    p.add_argument("url")
    p.add_argument("--verbose", action="store_true")
    a = p.parse_args()
    return inspect_url(a.url, a.verbose)


if __name__ == "__main__":
    raise SystemExit(main())
