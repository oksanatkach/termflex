import json
from collections import defaultdict
from pathlib import Path
import os
from typing import Union, Dict, List


JsonInput = Union[str, bytes, os.PathLike, Dict, List]

def parse_json_to_term_map(
    input_json: JsonInput,
    schema: Dict,
    encoding: str="utf-8",
):
    # 1. Path-like (Path, or anything implementing __fspath__)
    if isinstance(input_json, os.PathLike):
        with open(input_json, encoding=encoding) as f:
            data = json.load(f)

    # 2. Raw bytes: treat as JSON text (json.loads accepts bytes)
    elif isinstance(input_json, (bytes, bytearray)):
        data = json.loads(input_json)

    # 3. String: JSON text or a path?
    elif isinstance(input_json, str):
        stripped = input_json.lstrip()
        path = Path(stripped)
        if path.is_file():
            with open(input_json, encoding=encoding) as f:
                data = json.load(f)
        else:
            data = json.loads(stripped)
    # 4. Object with no need to parse
    elif isinstance(input_json, dict) or isinstance(input_json, list):
        data = input_json
    else:
        raise ValueError(
            f"Input is neither an existing file nor valid JSON: {input_json[:80]!r}"
        ) from None

    target_map = defaultdict(list)

    if isinstance(data, dict):
        data = data.get(schema['root'], [])

    # assume root is list for now
    for entry in data:
        src_terms = entry.get(schema["source"], [])
        tgt_terms = entry.get(schema["target"], [])

        if isinstance(src_terms, str):
            src_terms = [src_terms]
        if isinstance(tgt_terms, str):
            tgt_terms = [tgt_terms]

        for src in src_terms:
            for tgt in tgt_terms:
                if src and tgt:
                    target_map[src.strip()].append(tgt.strip())

    return target_map
