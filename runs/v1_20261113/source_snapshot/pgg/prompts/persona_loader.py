"""Parse personas/PERSONAS.md into {id: {principal_instruction, disposition}}.

Format: level-2 headings ``## persona: <id>``; under each, labelled fields
``principal_instruction:`` and ``disposition:`` (either may be empty). Text that
is not under a persona heading is ignored (it is documentation).
"""

from __future__ import annotations

import os
import re
from typing import Dict, Optional

from pydantic import BaseModel

_HEADING = re.compile(r"^##\s+persona:\s*(?P<id>[A-Za-z0-9_\-]+)\s*$")
_FIELD = re.compile(r"^(?P<key>principal_instruction|disposition)\s*:\s*(?P<val>.*)$")


class Persona(BaseModel):
    id: str
    principal_instruction: str = ""
    disposition: str = ""


def _clean(text: str) -> str:
    text = text.strip()
    # strip one layer of surrounding quotes if present
    if len(text) >= 2 and text[0] in "\"'" and text[-1] == text[0]:
        text = text[1:-1]
    return text.strip()


def parse_personas(markdown: str) -> Dict[str, Persona]:
    personas: Dict[str, Persona] = {}
    current_id: Optional[str] = None
    current_key: Optional[str] = None
    buffers: Dict[str, Dict[str, list]] = {}

    def flush_persona(pid: str) -> None:
        b = buffers.get(pid, {})
        personas[pid] = Persona(
            id=pid,
            principal_instruction=_clean("\n".join(b.get("principal_instruction", []))),
            disposition=_clean("\n".join(b.get("disposition", []))),
        )

    for raw in markdown.splitlines():
        line = raw.rstrip("\n")
        m = _HEADING.match(line.strip())
        if m:
            if current_id is not None:
                flush_persona(current_id)
            current_id = m.group("id")
            current_key = None
            buffers[current_id] = {"principal_instruction": [], "disposition": []}
            continue
        if line.strip().startswith("## "):
            # some other level-2 heading -> close any open persona
            if current_id is not None:
                flush_persona(current_id)
            current_id = None
            current_key = None
            continue
        if current_id is None:
            continue
        fm = _FIELD.match(line.strip())
        if fm:
            current_key = fm.group("key")
            buffers[current_id][current_key].append(fm.group("val"))
            continue
        if current_key is not None:
            buffers[current_id][current_key].append(line)

    if current_id is not None:
        flush_persona(current_id)
    return personas


def parse_single_persona(text: str, persona_id: str) -> Persona:
    """Parse one per-file persona (no ``## persona:`` heading; id is the filename).

    The file just contains the two labelled fields, in any order::

        principal_instruction: "..."
        disposition: ...

    A leading ``# ...`` title line is ignored, so people can title their file.
    """
    buffers: Dict[str, list] = {"principal_instruction": [], "disposition": []}
    current_key: Optional[str] = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped.startswith("#"):
            # a markdown title/comment line inside a per-file persona -> ignore
            current_key = None
            continue
        fm = _FIELD.match(stripped)
        if fm:
            current_key = fm.group("key")
            buffers[current_key].append(fm.group("val"))
            continue
        if current_key is not None:
            buffers[current_key].append(line)
    return Persona(
        id=persona_id,
        principal_instruction=_clean("\n".join(buffers["principal_instruction"])),
        disposition=_clean("\n".join(buffers["disposition"])),
    )


def load_personas(path: str) -> Dict[str, Persona]:
    """Load personas from either a single markdown file or a directory of files.

    - If ``path`` is a directory: every ``*.md`` in it is one persona, whose id is
      the filename without extension. Files named ``README*`` or starting with
      ``_`` are skipped (treated as docs). This is the layout for parallel
      editing — one person owns one file, so there are no merge conflicts.
    - If ``path`` is a single file: it is parsed as the multi-block
      ``## persona: <id>`` format.
    - If a directory also contains a ``PERSONAS.md``, that file's blocks are
      merged in too (per-file entries win on id collisions).
    """
    if os.path.isdir(path):
        personas: Dict[str, Persona] = {}
        for name in sorted(os.listdir(path)):
            if not name.endswith(".md"):
                continue
            if name.startswith("_") or name.lower().startswith("readme"):
                continue
            full = os.path.join(path, name)
            pid = os.path.splitext(name)[0]
            with open(full, "r", encoding="utf-8") as fh:
                text = fh.read()
            # A file is "multi-block" only if a real heading line matches
            # ``## persona: <id>`` — not merely because the text mentions it in
            # a comment. Check line by line so comment examples don't misroute.
            is_multi = any(_HEADING.match(ln.strip()) for ln in text.splitlines())
            if pid.lower() == "personas" or is_multi:
                for k, v in parse_personas(text).items():
                    personas.setdefault(k, v)
            else:
                personas[pid] = parse_single_persona(text, pid)
        return personas

    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return parse_personas(fh.read())
