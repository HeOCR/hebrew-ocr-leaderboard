"""Publish one validated results snapshot to the configured public HF surfaces."""

from hashlib import sha256
from pathlib import Path
import sys

from huggingface_hub import HfApi, hf_hub_download

from leaderboard_results import RESULTS_REPO, read_results

SPACE = "HeOCR/hebrew-ocr-leaderboard"
PATH = Path("out/results.json")


def sync(api, repo, kind, pin):
    info = api.repo_info(repo_id=repo, repo_type=kind)
    if info.private or info.gated:
        raise ValueError("The destination needs separate public-release approval")
    commit = api.upload_file(path_or_fileobj=PATH, path_in_repo="results.json", repo_id=repo, repo_type=kind)
    readback = hf_hub_download(repo, "results.json", repo_type=kind, revision=commit.oid, token=False)
    if sha256(Path(readback).read_bytes()).hexdigest() != pin:
        raise ValueError("Hugging Face results readback differs")
    print(f"{kind} {commit.oid} {pin}")


if __name__ == "__main__":
    try:
        read_results(PATH)
        digest = sha256(PATH.read_bytes()).hexdigest()
        api = HfApi()
        sync(api, RESULTS_REPO, "dataset", digest)
        sync(api, SPACE, "space", digest)
    except Exception:
        # Registry exceptions may contain temporary download URLs.
        print("Results sync failed. Check destination access and the aggregate pin.", file=sys.stderr)
        raise SystemExit(1)
