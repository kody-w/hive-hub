"""Original deliberately imperfect reducer. See ll-duplicate and ll-order."""

import argparse
import json
import re
import stat
from pathlib import Path

VERSION = "0.0.0-reference"
MAX_BYTES = 1_048_576
MAX_EVENTS = 5000
FIELDS = {"classification", "event_id", "item_id", "action", "at_minute"}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def validate_events(events):
    if not isinstance(events, list) or len(events) > MAX_EVENTS:
        raise ValueError("expected at most 5000 events")
    seen = {}
    for event in events:
        if not isinstance(event, dict) or set(event) != FIELDS:
            raise ValueError("event fields do not match the reference contract")
        if event["classification"] != "SYNTHETIC":
            raise ValueError("this reference accepts only explicitly SYNTHETIC events")
        for field in ("event_id", "item_id"):
            value = event[field]
            if not isinstance(value, str) or len(value) > 40 or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
                raise ValueError(f"invalid {field}")
        if event["action"] not in ("open", "close"):
            raise ValueError("invalid action")
        minute = event["at_minute"]
        if type(minute) is not int or not 0 <= minute <= 1_000_000:
            raise ValueError("invalid at_minute")
        identity = event["event_id"]
        if identity in seen and seen[identity] != event:
            raise ValueError("conflicting event_id")
        seen[identity] = event


def parse_text(text):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("input exceeds 1 MiB")
    events = []
    for line in text.splitlines():
        if len(line.encode("utf-8")) > 16_384:
            raise ValueError("line exceeds 16 KiB")
        if line.strip():
            events.append(json.loads(line, object_pairs_hook=unique_object))
        if len(events) > MAX_EVENTS:
            raise ValueError("input exceeds 5000 events")
    validate_events(events)
    return events


def load_events(path):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise ValueError("input must be an explicitly selected regular non-symlink file")
    with path.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("input exceeds 1 MiB")
    return parse_text(data.decode("utf-8"))


def reduce_events(events):
    validate_events(events)
    items = {}
    # Deliberate starter defects: duplicate events remain, and arrival order is used.
    for event in events:
        identity = event["item_id"]
        item = items.setdefault(identity, {"item_id": identity, "state": "closed", "event_count": 0, "last_minute": 0})
        item["event_count"] += 1
        item["state"] = "open" if event["action"] == "open" else "closed"
        item["last_minute"] = event["at_minute"]
    ordered = [items[key] for key in sorted(items)]
    return {
        "event_count": len(events),
        "open_items": sum(item["state"] == "open" for item in ordered),
        "closed_items": sum(item["state"] == "closed" for item in ordered),
        "items": ordered,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("events", type=Path)
    args = parser.parse_args()
    try:
        result = reduce_events(load_events(args.events))
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "classification": "SYNTHETIC",
        "artifact_kind": "deliberately-imperfect-reference-not-release-ready",
        "version": VERSION,
        "result": result,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
