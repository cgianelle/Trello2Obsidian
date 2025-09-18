#!/usr/bin/env python3
"""Enhance existing Markdown notes using an LM Studio hosted model.

The script reads an existing Markdown note that follows the lm-studio
template, extracts the "SECTION 1: INTRODUCTION/OVERVIEW" content, and
asks an LLM served through the LM Studio OpenAI-compatible API to
populate "SECTION 2" and "SECTION 3".  The resulting note is written to
an output directory while preserving the original filename.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests

SECTION_INTRO = "## SECTION 1: INTRODUCTION/OVERVIEW"
SECTION_CONCEPTS = "## SECTION 2: KEY CONCEPTS/DEFINITIONS"
SECTION_EVIDENCE = "## SECTION 3: EVIDENCE/SUPPORTING DETAILS"
SECTION_HEADING_PREFIX = "## SECTION "
TAGS_PREFIX = "tags:"


@dataclass
class ModelResponse:
    tags: list[str]
    section2: str
    section3: str


@dataclass
class Section:
    heading: str
    start: int
    end: int

    @property
    def body_start(self) -> int:
        return self.start + len(self.heading)


class NoteStructureError(RuntimeError):
    """Raised when the input note does not match the expected template."""


def iter_sections(text: str) -> Iterable[Section]:
    """Yield ``Section`` objects for every level-two heading in *text*."""

    start = 0
    while True:
        start = text.find(SECTION_HEADING_PREFIX, start)
        if start == -1:
            return
        line_end = text.find("\n", start)
        if line_end == -1:
            line_end = len(text)
        heading = text[start:line_end]

        next_start = text.find(SECTION_HEADING_PREFIX, line_end)
        if next_start == -1:
            next_start = len(text)
        yield Section(heading=heading, start=start, end=next_start)
        start = next_start


def get_required_section(text: str, heading: str) -> Section:
    for section in iter_sections(text):
        if section.heading.strip() == heading:
            return section
    raise NoteStructureError(f"Section with heading '{heading}' not found.")


def extract_intro(text: str) -> str:
    section = get_required_section(text, SECTION_INTRO)
    return text[section.body_start:section.end].strip()


def build_prompt(introduction: str) -> list[dict[str, str]]:
    system_prompt = (
        "You expand study notes. Given the introduction section of a note, "
        "write concise, information-rich content for the Key Concepts and "
        "Evidence sections of the same note. You also suggest relevant tags. "
        "ALWAYS respond with valid minified JSON using this schema: "
        "{\"tags\": [tag_strings], \"section2\": \"markdown\", \"section3\": \"markdown\"}."
    )
    user_prompt = """You are provided the introduction section of a note:
"""
    user_prompt += f"""
<INTRODUCTION>
{introduction}
</INTRODUCTION>

Using only the information above and widely accepted background knowledge:
- Provide 3 to 6 short, topical tags (single or hyphenated words) that reflect the introduction.
- Draft the Key Concepts and Evidence sections using Markdown and keep the headings exactly as shown below.
- Each section must contain at least three well-developed bullet points.
- Do not add extra headings or commentary.

Return the result as minified JSON in this form (without extra prose):
{{"tags":["tag1","tag2"],"section2":"## SECTION 2: KEY CONCEPTS/DEFINITIONS\n*   ...","section3":"## SECTION 3: EVIDENCE/SUPPORTING DETAILS\n*   ..."}}
"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def call_chat_completion(
    api_base: str,
    model: str,
    messages: list[dict[str, str]],
    api_key: str | None = None,
    temperature: float = 0.3,
) -> str:
    url = api_base.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }

    response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=120)
    if response.status_code != 200:
        raise RuntimeError(
            f"LLM request failed with status {response.status_code}: {response.text}"
        )

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Unexpected response schema: {data!r}") from exc


def parse_model_response(raw: str) -> ModelResponse:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Model response was not valid JSON.") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"Model response JSON must be an object, got {type(payload).__name__}.")

    try:
        tags_raw = payload["tags"]
        section2 = payload["section2"]
        section3 = payload["section3"]
    except KeyError as exc:
        raise RuntimeError(f"Model response missing key: {exc.args[0]}") from exc

    if not isinstance(tags_raw, list) or not all(isinstance(tag, str) for tag in tags_raw):
        raise RuntimeError("Model response 'tags' must be a list of strings.")
    if not isinstance(section2, str) or not isinstance(section3, str):
        raise RuntimeError("Model response sections must be strings.")

    tags = [tag.strip() for tag in tags_raw if tag.strip()]
    if not tags:
        raise RuntimeError("Model did not provide any usable tags.")

    return ModelResponse(tags=tags, section2=section2.strip(), section3=section3.strip())


def ensure_required_headings(text: str) -> None:
    missing = [
        heading
        for heading in (SECTION_CONCEPTS, SECTION_EVIDENCE)
        if heading not in text
    ]
    if missing:
        raise RuntimeError(
            "LLM response missing required headings: " + ", ".join(missing)
        )


def format_tags(tags: Iterable[str]) -> str:
    cleaned = []
    seen = set()
    for tag in tags:
        normalized = tag.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)
    if not cleaned:
        raise RuntimeError("No valid tags to write.")
    return json.dumps(cleaned, ensure_ascii=False)


def replace_tags(text: str, tags: Iterable[str]) -> str:
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if line.strip().startswith(TAGS_PREFIX):
            prefix, _, _ = line.partition(TAGS_PREFIX)
            lines[idx] = f"{prefix}{TAGS_PREFIX} {format_tags(tags)}"
            return "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    raise NoteStructureError("Could not locate 'tags:' line in note front matter.")


def merge_sections(original: str, replacement: str) -> str:
    ensure_required_headings(replacement)
    section2 = get_required_section(original, SECTION_CONCEPTS)
    section3 = get_required_section(original, SECTION_EVIDENCE)

    # Everything before SECTION 2 remains untouched.
    prefix = original[: section2.start]

    # Everything after SECTION 3 should be preserved.
    tail_start = section3.end
    tail = original[tail_start:]

    replacement_block = replacement.strip() + "\n\n"
    return prefix + replacement_block + tail.lstrip("\n")


def enhance_note(
    note_path: Path,
    output_dir: Path,
    api_base: str,
    model: str,
    api_key: str | None,
    temperature: float,
) -> Path:
    text = note_path.read_text(encoding="utf-8")
    introduction = extract_intro(text)

    messages = build_prompt(introduction)
    completion = call_chat_completion(
        api_base=api_base,
        model=model,
        messages=messages,
        api_key=api_key,
        temperature=temperature,
    )

    model_response = parse_model_response(completion)
    sections_markdown = f"{model_response.section2}\n\n{model_response.section3}".strip()
    enhanced = merge_sections(text, sections_markdown)
    enhanced = replace_tags(enhanced, model_response.tags)

    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / note_path.name
    destination.write_text(enhanced, encoding="utf-8")
    return destination


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Populate SECTION 2 and SECTION 3 of a Markdown note using an "
            "LM Studio hosted model."
        )
    )
    parser.add_argument("note", type=Path, help="Path to the source Markdown note")
    parser.add_argument(
        "output_dir", type=Path, help="Directory where the enhanced note will be written"
    )
    parser.add_argument(
        "--api-base",
        default=os.environ.get("LM_STUDIO_API_BASE", "http://localhost:1234/v1"),
        help=(
            "Base URL for the LM Studio OpenAI-compatible endpoint. "
            "Defaults to http://localhost:1234/v1 or the LM_STUDIO_API_BASE env var."
        ),
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("LM_STUDIO_MODEL", "google/gemma-3-27b"),
        help="Model name to request from the LM Studio API (default: google/gemma-3-27b)",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("LM_STUDIO_API_KEY"),
        help="Optional API key for authenticated LM Studio instances",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.3,
        help="Sampling temperature to use for the completion (default: 0.3)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.note.is_file():
        raise SystemExit(f"Input note not found: {args.note}")

    try:
        destination = enhance_note(
            note_path=args.note,
            output_dir=args.output_dir,
            api_base=args.api_base,
            model=args.model,
            api_key=args.api_key,
            temperature=args.temperature,
        )
    except NoteStructureError as exc:
        raise SystemExit(str(exc)) from exc
    except requests.RequestException as exc:
        raise SystemExit(f"Failed to contact LM Studio API: {exc}") from exc
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print(f"Enhanced note written to {destination}")
    return 0


if __name__ == "__main__":  # pragma: no cover - command line usage
    sys.exit(main())
