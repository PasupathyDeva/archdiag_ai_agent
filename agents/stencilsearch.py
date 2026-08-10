#!/usr/bin/env python3
"""
stencilsearch.py - look up draw.io shape styles in the local stencil libraries.

The local libraries are draw.io .xml "mxlibrary" files whose entries embed the
icon as a self-contained data URI (shape=image;image=data:image/svg+xml,<base64>).
Because the image travels inside the style string, shapes found this way render
everywhere: draw.io desktop, web, and the headless CLI export.

Usage
-----
  # search all libraries by name
  python stencilsearch.py "data lake storage gen2"

  # limit results / search one library folder
  python stencilsearch.py "power bi" --limit 3
  python stencilsearch.py snowflake --root "<other folder>"

  # print the full style string ready to paste into an mxCell
  python stencilsearch.py "data lake storage gen2" --style

  # turn any local .svg/.png into a drawio image style (for logos that are not
  # packaged as a library, e.g. the Snowflake brand assets)
  python stencilsearch.py --file "C:\\path\\to\\snowflake-bug-color-rgb.svg"

Matching ignores case, hyphens, underscores and spaces, so "data lake storage
gen2" matches "10091-icon-service-Data-Lake-Storage-Gen2".
"""

import argparse
import base64
import html
import json
import mimetypes
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(
    r"C:\Users\edevpas\OneDrive - Ericsson\Documents\MYFOLDER-HardDisk\MY FOLDER\IDAP\DrawioStencils"
)

STYLE_RE = re.compile(r'style="([^"]*)"')


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def iter_library_entries(root: Path):
    """Yield (library_path, title, w, h, style) for every entry in every library."""
    for path in sorted(root.rglob("*.xml")):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "<mxlibrary>" not in raw:
            continue
        try:
            start = raw.index("[")
            end = raw.rindex("]") + 1
            entries = json.loads(raw[start:end])
        except (ValueError, json.JSONDecodeError):
            continue
        for entry in entries:
            title = entry.get("title") or ""
            xml = html.unescape(entry.get("xml") or "")
            match = STYLE_RE.search(xml)
            if not match:
                continue
            yield path, title, entry.get("w"), entry.get("h"), match.group(1)


def search(root: Path, query: str, limit: int, show_style: bool) -> int:
    needle = normalise(query)
    hits = []
    for path, title, w, h, style in iter_library_entries(root):
        if needle in normalise(title):
            hits.append((path, title, w, h, style))

    if not hits:
        print(f'No stencil matched "{query}" under {root}')
        return 1

    # Prefer the shortest (closest) titles first.
    hits.sort(key=lambda item: (len(normalise(item[1])), item[1]))
    for path, title, w, h, style in hits[:limit]:
        print(f"title  : {title}")
        print(f"library: {path.name}")
        print(f"size   : w={w} h={h}")
        if show_style:
            print(f"style  : {style}")
        else:
            print(f"style  : {style[:120]}... [{len(style)} chars, use --style for full]")
        print("-" * 70)
    if len(hits) > limit:
        print(f"({len(hits) - limit} more matches, raise --limit to see them)")
    return 0


def style_from_file(path: Path) -> int:
    if not path.is_file():
        print(f"Not a file: {path}")
        return 1
    mime = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    # draw.io expects "data:<mime>,<base64>" - the standard ";base64" marker
    # is NOT understood by its image renderer and the shape renders empty.
    style = (
        "shape=image;verticalLabelPosition=bottom;verticalAlign=top;imageAspect=0;"
        f"aspect=fixed;image=data:{mime},{data}"
    )
    print(f"file   : {path.name}")
    print(f"mime   : {mime}")
    print(f"style  : {style}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("query", nargs="?", help="stencil name to search for")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="stencil library root folder")
    parser.add_argument("--limit", type=int, default=5, help="max results (default 5)")
    parser.add_argument("--style", action="store_true", help="print the full style string")
    parser.add_argument("--file", type=Path, help="build an image style from a local .svg/.png instead of searching")
    args = parser.parse_args()

    if args.file:
        return style_from_file(args.file)
    if not args.query:
        parser.error("provide a search query or --file")
    if not args.root.is_dir():
        print(f"Stencil root not found: {args.root}")
        return 1
    return search(args.root, args.query, args.limit, args.style)


if __name__ == "__main__":
    sys.exit(main())
