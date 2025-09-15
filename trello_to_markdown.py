#!/usr/bin/env python3
"""Convert Trello comments to standalone Markdown files.

This script reads a Trello board export JSON file and creates a
Markdown file for each comment.  The resulting files can be imported
into Obsidian or any other Markdown based note system.

Example usage:
    python trello_to_markdown.py board.json -o notes
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).with_name("templates")
env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
NOTE_TEMPLATE = env.get_template("lm-studio-template.md")


def slugify(value: str) -> str:
    """Return a filesystem friendly slug for *value*.

    Only the characters ``a-z`` and ``0-9`` are kept; everything else is
    replaced by ``-``.  Multiple ``-`` characters are collapsed into
    one, and leading/trailing ``-`` are stripped.  An empty result
    returns ``"card"``.
    """
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "card"


def convert(json_file: Path, out_dir: Path) -> int:
    """Create Markdown files for each comment in ``json_file``.

    Parameters
    ----------
    json_file:
        Path to the Trello board export JSON file.
    out_dir:
        Directory where Markdown files should be written.  It will be
        created if it doesn't already exist.

    Returns
    -------
    int
        Number of Markdown files written.
    """
    with open(json_file, encoding="utf-8") as f:
        data = json.load(f)

    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    for action in data.get("actions", []):
        if action.get("type") != "commentCard":
            continue

        card_name = action["data"]["card"]["name"]
        comment = action["data"]["text"]
        date = action.get("date", "")
        comment_id = action.get("id", "")

        card_slug = slugify(card_name)
        filename = f"{date[:10]}_{card_slug}_{comment_id}.md"
        filepath = out_dir / filename

        content = NOTE_TEMPLATE.render(
            card_name=card_name, note=comment, date=date
        )
        filepath.write_text(content, encoding="utf-8")

        count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert Trello comments to Markdown notes",
    )
    parser.add_argument("json_file", help="Trello board export JSON file")
    parser.add_argument(
        "-o",
        "--output",
        default="notes",
        help="Output directory for Markdown files (default: notes)",
    )

    args = parser.parse_args()
    json_path = Path(args.json_file)
    out_path = Path(args.output)

    written = convert(json_path, out_path)
    print(f"Wrote {written} Markdown files to {out_path}")


if __name__ == "__main__":  # pragma: no cover - manual invocation
    main()
