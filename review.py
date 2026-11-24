"""Score immutable submission packets without checking out contributor code."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from unicodedata import normalize
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

from leaderboard_results import SHA, STRATA, VIEWS, percentage, read_results, text, validate
from submissions import MAX_UPLOAD, score_registered_upload

MAX_PACKET = 8192
COMMIT = re.compile(r"[a-f0-9]{40}")
RECEIPT = re.compile(r"submissions/[a-z0-9][a-z0-9-]{0,63}\.json")
HF_LINK = re.compile(
    r"https://huggingface\.co/datasets/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/resolve/[a-f0-9]{40}"
    r"(/[A-Za-z0-9_.-]+)+\.zip"
)
HF_DOWNLOAD_HOST = re.compile(
    r"(huggingface\.co|cdn-lfs(?:-[a-z0-9-]+)?\.hf\.co|cas-bridge\.xethub\.hf\.co)"
)


class HFRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if (target.scheme != "https" or target.netloc != target.hostname or not target.hostname
                or not HF_DOWNLOAD_HOST.fullmatch(target.hostname)):
            raise ValueError("Unexpected Hugging Face download destination")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def fetch_hf(url):
    if not HF_LINK.fullmatch(url) or any(part in (".", "..") for part in urlsplit(url).path.split("/")):
        raise ValueError("Use a public, commit-pinned Hugging Face dataset ZIP URL")
    try:
        with build_opener(HFRedirects()).open(url, timeout=20) as response:
            return response.read(MAX_UPLOAD + 1)
    except OSError as exc:
        raise ValueError("Could not download the public prediction ZIP") from exc


class DuplicateSubmission(ValueError):
    pass


def reader_key(metadata):
    """Ignore case, Unicode compatibility variants, and differences in spacing."""
    return tuple(" ".join(normalize("NFKC", metadata[key]).casefold().split())
                 for key in ("reader", "version"))


def packet(raw):
    if len(raw) > MAX_PACKET:
        raise ValueError("Submission receipt exceeds 8 KiB")
    value = json.loads(raw)
    fields = {"sha256", "reader", "version", "license", "weights", "link"}
    optional = {"reader_type", "hf_url"}
    if not isinstance(value, dict) or not fields <= value.keys() <= fields | optional:
        raise ValueError("Invalid submission receipt fields")
    if not isinstance(value["sha256"], str) or not SHA.fullmatch(value["sha256"]):
        raise ValueError("Prediction ZIP SHA-256 is required")
    if not all(text(value[key], size) for key, size in (("reader", 80), ("version", 60), ("license", 80))):
        raise ValueError("Use short public reader, version and licence labels")
    if re.match(r"^heocr\b", reader_key(value)[0]):
        raise ValueError("Use the external reader's public name")
    if value["weights"] not in ("open", "closed"):
        raise ValueError("Declare open or closed weights")
    distribution = f'{value["weights"]} weights'
    value.setdefault("reader_type", distribution)
    if value["reader_type"] not in (distribution, "API"):
        raise ValueError("Invalid reader distribution type")
    link = value["link"]
    if not text(link, 512) or any(c.isspace() for c in link):
        raise ValueError("Link to the public reader or its documentation")
    target = urlsplit(link)
    if target.scheme != "https" or not target.hostname or target.username is not None:
        raise ValueError("Use a public HTTPS reader link without credentials")
    if "hf_url" in value and not isinstance(value["hf_url"], str):
        raise ValueError("Invalid Hugging Face ZIP link")
    return value

def git(*args):
    return subprocess.run(("git", *args), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def read_blob(commit, path, limit):
    kind = git("ls-tree", "-z", commit, "--", path).split(b" ", 2)[:2]
    if kind != [b"100644", b"blob"]:
        raise ValueError("Submission entries must be ordinary, non-executable files")
    locator = f"{commit}:{path}"
    if int(git("cat-file", "-s", locator)) > limit:
        raise ValueError("Submission file exceeds its size limit")
    return git("cat-file", "blob", locator)


def read_pair(commit, path, changed=None):
    if not RECEIPT.fullmatch(path):
        raise ValueError("Use submissions/<id>.json")
    entry = packet(read_blob(commit, path, MAX_PACKET))
    zip_path = path.removesuffix(".json") + ".zip"
    expected = {path} if "hf_url" in entry else {path, zip_path}
    if changed is not None and changed != expected:
        raise ValueError("Add only the receipt and its matching ZIP, or the receipt and a Hugging Face link")
    return entry, zip_path


def score_packet(commit, entry, zip_path):
    raw = fetch_hf(entry["hf_url"]) if "hf_url" in entry else read_blob(commit, zip_path, MAX_UPLOAD)
    if not 0 < len(raw) <= MAX_UPLOAD or sha256(raw).hexdigest() != entry["sha256"]:
        raise ValueError("Prediction ZIP failed its size or SHA-256 check")
    return score_registered_upload(raw, entry)


def changed_paths(base, head):
    raw = git("diff", "--no-ext-diff", "--no-renames", "--name-status", "-z", base, head).split(b"\0")[:-1]
    if len(raw) not in (2, 4) or raw[::2] != [b"A"] * (len(raw) // 2):
        raise ValueError("A submission PR may only add one new packet")
    return {item.decode("ascii") for item in raw[1::2]}


def score_pr(number, expected_head):
    if not 0 < number < 10**9 or not COMMIT.fullmatch(expected_head):
        raise ValueError("Use a PR number and its exact 40-character head SHA")
    base = git("rev-parse", "HEAD").decode().strip()
    git("fetch", "--quiet", "--no-tags", "origin", f"refs/pull/{number}/head")
    head = git("rev-parse", "FETCH_HEAD").decode().strip()
    if head != expected_head:
        raise ValueError("PR head moved before review")
    ancestor = git("merge-base", base, head).decode().strip()
    changed = changed_paths(ancestor, head)
    receipts = [path for path in changed if RECEIPT.fullmatch(path)]
    if len(receipts) != 1:
        raise ValueError("A submission PR must contain exactly one receipt")
    path = receipts[0]
    entry, zip_path = read_pair(head, path, changed)
    existing = read_results(Path("results.json"))
    occupied = git("ls-tree", "-z", base, "--", *sorted(changed))
    if occupied or any(row["id"] == entry["sha256"] for row in existing["rows"]):
        raise ValueError("Submission filename or ZIP already exists on main")
    key = reader_key(entry)
    accepted = (read_pair(base, receipt.as_posix())[0] for receipt in Path("submissions").glob("*.json"))
    if any(reader_key(row) == key for row in existing["rows"]) or any(reader_key(row) == key for row in accepted):
        raise DuplicateSubmission("This reader and version already have a submission on main.")
    row = score_packet(head, entry, zip_path)
    validate({**existing, "rows": [*existing["rows"], row]})
    return {"pull_request": number, "head_sha": head, "row": row}


def reconcile(path):
    data = read_results(path)
    known = {row["id"] for row in data["rows"]}
    reader_versions = {reader_key(row) for row in data["rows"]}
    commit = git("rev-parse", "HEAD").decode().strip()
    for receipt in sorted(Path("submissions").glob("*.json")):
        entry, zip_path = read_pair(commit, receipt.as_posix())
        pin = entry["sha256"]
        key = reader_key(entry)
        if pin in known:
            continue
        if key in reader_versions:
            print("Skipped duplicate reader and version.", file=sys.stderr)
            continue
        data["rows"].append(score_packet(commit, entry, zip_path))
        known.add(pin)
        reader_versions.add(key)
    validate(data)
    return data


def pr_comment(result):
    """Render only scorer metrics and the validated head, never uploaded labels or text."""
    head = result["head_sha"]
    if not COMMIT.fullmatch(head):
        raise ValueError("Invalid score receipt head")
    lines = [
        "### P-mod-open v0 submission score",
        "",
        f"Scored PR head `{head}` with pinned heocr-bench on the 65 public carriers.",
        "",
        "**Self-submitted, unverified.** Maintainer review is required before merge.",
        "",
        "| Scope | Common filtered CER | All-reference CER |",
        "| --- | ---: | ---: |",
    ]
    views = result["row"]["views"]
    for key, (label, _) in STRATA.items():
        filtered, all_ref = (percentage(views[view][key]) for view in VIEWS)
        lines.append(f"| {label} | {filtered} | {all_ref} |")
    return "\n".join(lines) + "\n"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    path.write_bytes(raw)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("pr")
    review.add_argument("number", type=int)
    review.add_argument("head")
    review.add_argument("output", type=Path)
    review.add_argument("--comment", type=Path)
    sync = sub.add_parser("reconcile")
    sync.add_argument("results", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "pr":
            result = score_pr(args.number, args.head)
            write_json(args.output, result)
            if args.comment:
                args.comment.write_text(pr_comment(result), encoding="utf-8")
        else:
            current = read_results(args.results)
            merged = reconcile(args.results)
            if merged != current:
                write_json(args.results, merged)
            print(f"{len(merged['rows'])} aggregate rows")
    except DuplicateSubmission as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        # Third-party parsers and network errors can include prediction text or signed URLs.
        print("Submission receipt, ZIP, or pinned scoring failed. See SUBMITTING.md.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
