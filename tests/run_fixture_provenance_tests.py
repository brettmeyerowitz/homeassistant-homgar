"""Provenance invariants for the payload corpus.

The corpus is what every decoder claim is checked against, so a sample that
says where it came from has to be telling the truth. These checks are the ones
that can be made offline; they will not catch a payload that was quietly edited
by hand, but they do catch the shapes that mistake takes in practice - the same
string filed under two models, or a sample asserting an issue as its source
with no issue recorded.

No pytest, so this runs both on the host and inside the ha-test container.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path


def _find_repo_root() -> Path:
    for start in (Path(__file__).resolve().parent, Path.cwd(), Path("/config")):
        current = start
        while True:
            if (current / "tests" / "fixtures" / "payloads").exists():
                return current
            if current.parent == current:
                break
            current = current.parent
    raise RuntimeError("Could not locate the payload fixture directory")


ROOT = _find_repo_root()
PAYLOADS = ROOT / "tests" / "fixtures" / "payloads"

# Where a sample came from. The first three assert that the payload appears
# verbatim in that source; "unverified" says the origin was never established
# and the sample must not be cited as evidence on its own.
SOURCE_TYPES = {
    "github_issue",
    "github_issue_comment",
    "reporter_app_verified",
    "live_capture",
    "maintainer_device",
    "unverified",
}
CLAIMS_AN_ISSUE = {"github_issue", "github_issue_comment"}

PASS = 0
FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}{': ' + detail if detail else ''}")


def main() -> int:
    payload_owners: dict[str, list[str]] = defaultdict(list)

    for path in sorted(PAYLOADS.glob("*.json")):
        data = json.loads(path.read_text())
        model = data["model"]
        print(f"\n🧪 {model}")
        seen_ids: set[str] = set()

        for sample in data.get("samples", []):
            sid = sample.get("id", "<no id>")
            where = f"{model}/{sid}"

            check(f"{sid} has a unique id", sid not in seen_ids)
            seen_ids.add(sid)

            source_type = sample.get("source_type")
            check(f"{sid} declares a known source_type",
                  source_type in SOURCE_TYPES, str(source_type))

            if source_type in CLAIMS_AN_ISSUE:
                check(f"{sid} records the issue it claims",
                      sample.get("source_issue") is not None)

            if source_type == "unverified":
                check(f"{sid} explains why it is unverified",
                      bool(sample.get("provenance")))

            payload = sample.get("payload")
            check(f"{sid} has a payload", bool(payload))
            if payload:
                payload_owners[payload].append(where)

    print("\n🧪 Cross-model payload reuse")
    shared = {
        payload: owners
        for payload, owners in payload_owners.items()
        if len({owner.split("/")[0] for owner in owners}) > 1
    }
    check("no payload is filed under more than one model",
          not shared,
          "; ".join(f"{p[:32]}... -> {owners}" for p, owners in shared.items()))

    total = PASS + FAIL
    print(f"\n{'=' * 50}")
    print(f"Fixture provenance results: {PASS}/{total} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
