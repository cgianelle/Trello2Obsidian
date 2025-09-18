# Trello2Obsidian

A small utility to convert a Trello board export into individual Markdown notes for Obsidian. Each comment left on a Trello card becomes its own Markdown file, named after the card and comment timestamp. This allows reading notes captured in Trello to be linked and organized in Obsidian.

## Requirements

- Python 3.8 or newer

## Setup

Use a virtual environment to isolate the project's dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

1. Export your Trello board as JSON.
2. Run the converter specifying the JSON file and an output directory:

```bash
python trello_to_markdown.py 'r6MMYk8s - reading-list.json' -o notes
```

The script will create one Markdown file per comment inside the `notes` directory.

The note layout is driven by the Jinja2 template in `templates/lm-studio-template.md`.
Edit this file to adjust section headings or formatting.

## Enhancing notes with LM Studio

After generating Markdown notes you can expand their "Key Concepts" and
"Evidence" sections using a local LM Studio instance. The script also
refreshes the front-matter tag list so it reflects the enhanced content:

```bash
python enhance_note.py path/to/note.md enhanced-notes/
```

By default the script contacts `http://localhost:1234/v1` and requests
the `google/gemma-3-27b` model. Override the endpoint, model, or API key
with the `--api-base`, `--model`, and `--api-key` options (or the
`LM_STUDIO_API_BASE`, `LM_STUDIO_MODEL`, `LM_STUDIO_API_KEY`
environment variables).
