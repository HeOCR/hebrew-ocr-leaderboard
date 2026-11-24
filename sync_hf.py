"""Publish one validated results snapshot to the configured public HF surfaces."""

from hashlib import sha256
from pathlib import Path
import sys

from huggingface_hub import CommitOperationAdd, HfApi, hf_hub_download

from leaderboard_results import RESULTS_REPO, read_results

SPACE = "HeOCR/hebrew-ocr-leaderboard"
PATH = Path("out/results.json")


def sync(api, repo, kind, pin):
    info = api.repo_info(repo_id=repo, repo_type=kind)
    if info.private or info.gated:
        raise ValueError("The destination needs separate public-release approval")
    files = {"results.json": PATH}
    if kind == "space":
        if info.sdk != "static":
            raise ValueError("The approved leaderboard Space uses the static SDK")
        files.update({name: Path("space") / name for name in ("index.html", "leaderboard.js", "style.css")})
    commit = api.create_commit(
        repo, repo_type=kind, parent_commit=info.sha, commit_message="Sync leaderboard results",
        operations=[CommitOperationAdd(path_in_repo=name, path_or_fileobj=str(path))
                    for name, path in files.items()],
    )
    for name, path in files.items():
        downloaded = hf_hub_download(repo, name, repo_type=kind, revision=commit.oid, token=False)
        if Path(downloaded).read_bytes() != path.read_bytes():
            raise ValueError("Hugging Face leaderboard readback differs")
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
