#!/usr/bin/env python3
"""Lightweight publish-safety checks for this repository.

Runs without third-party dependencies so it can be used in CI and locally.
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_FILE_PATTERNS = (
    "credentials.json",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "*.crt",
    "*.cer",
    "*.pfx",
    "*id_rsa*",
)

TEXT_EXTENSIONS = {
    ".py",
    ".toml",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".ini",
    ".cfg",
    ".sh",
    ".env",
    ".lock",
}

SECRET_PATTERNS = (
    re.compile(r"GOCSPX-[A-Za-z0-9_-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ASIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:authorization)\s*:\s*bearer\s+[A-Za-z0-9._=-]{10,}"),
    re.compile(r"(?i)\"client_secret\"\s*:\s*\"(?!YOUR_CLIENT_SECRET)[^\"]+\""),
)


def run_git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def tracked_files() -> list[str]:
    raw = run_git("ls-files", "-z")
    return [f for f in raw.split("\0") if f]


def is_text_candidate(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    # Also scan extensionless tracked files (e.g. LICENSE, Dockerfile)
    return "." not in path.name


def main() -> int:
    failures: list[str] = []
    files = tracked_files()

    for rel in files:
        for pattern in FORBIDDEN_FILE_PATTERNS:
            if fnmatch.fnmatch(rel, pattern):
                failures.append(f"Forbidden file is tracked: {rel}")
                break

    for rel in files:
        path = ROOT / rel
        if not path.exists() or not path.is_file():
            continue
        if not is_text_candidate(path):
            continue

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for idx, line in enumerate(content.splitlines(), start=1):
            for pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    failures.append(
                        f"Potential secret pattern in {rel}:{idx} -> {pattern.pattern}"
                    )

    if failures:
        print("Security check failed:")
        for finding in failures:
            print(f"- {finding}")
        print(
            "\nFix findings before pushing. "
            "If a match is intentional test data, replace it with a clear placeholder."
        )
        return 1

    print("Security check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

