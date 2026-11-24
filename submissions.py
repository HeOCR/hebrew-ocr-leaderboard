"""Validate heocr-bench uploads and attach only aggregate results."""

from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, distribution
from io import BytesIO
import json
import os
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

from leaderboard_results import MANIFEST, STRATA, VIEWS, text

MAX_UPLOAD = 2_000_000
MAX_ENTRY = 32_768
MAX_EXPANDED = 512_000


def unpack_predictions(raw, carriers, destination):
    """Read the exact flat scorer roster into an isolated directory."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_UPLOAD:
        raise ValueError("Upload a ZIP no larger than 2 MB.")
    expected = {"metadata.json", *(f"{carrier}.txt" for carrier in carriers)}
    try:
        with ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) != len(expected) or {f.filename for f in entries} != expected:
                raise ValueError("ZIP entries must be the exact heocr-bench roster and metadata.json.")
            if sum(e.file_size for e in entries) > MAX_EXPANDED:
                raise ValueError("Expanded predictions exceed the upload limit.")
            for entry in entries:
                mode = stat.S_IFMT(entry.external_attr >> 16)
                if entry.is_dir() or mode not in (0, stat.S_IFREG) or entry.flag_bits & 1:
                    raise ValueError("Use regular unencrypted files in the ZIP.")
                if entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED) or entry.file_size > MAX_ENTRY:
                    raise ValueError("Use stored or deflated text files under 32 KiB each.")
                with archive.open(entry) as member:
                    content = member.read(MAX_ENTRY + 1)
                if len(content) != entry.file_size or len(content) > MAX_ENTRY:
                    raise ValueError("ZIP entry exceeds the upload limit.")
                content.decode("utf-8", errors="strict")
                (destination / entry.filename).write_bytes(content)
    except (BadZipFile, RuntimeError, UnicodeError) as exc:
        raise ValueError("Use a ZIP of UTF-8 prediction files.") from exc


def scorer_identity(expected):
    try:
        package = distribution("heocr-bench")
    except PackageNotFoundError as exc:
        raise RuntimeError("The pinned scorer is unavailable.") from exc
    origin = json.loads(package.read_text("direct_url.json") or "{}")
    if origin.get("url", "").removesuffix(".git") != "https://github.com/HeOCR/heocr-bench":
        raise RuntimeError("The scorer source did not match its registry.")
    if origin.get("vcs_info", {}).get("commit_id") != expected:
        raise RuntimeError("The scorer commit did not match its registry.")
    return f"heocr-bench {package.version}@{expected}"


@lru_cache(maxsize=1)
def benchmark_carriers():
    from heocr_bench.data import load_carriers, split_descriptor

    descriptor = split_descriptor("p-mod-open-v0", "test")
    if descriptor["manifest_sha256"] != MANIFEST:
        raise RuntimeError("Benchmark manifest differs from the leaderboard.")
    carriers = load_carriers(descriptor, None)
    if len(carriers) != 65:
        raise RuntimeError("Incomplete benchmark roster.")
    return carriers


def score_zip(raw, receipt, carriers, load_submission, score_submission, scorer_version):
    with TemporaryDirectory(prefix="heocr-predictions-") as temporary:
        folder = Path(temporary)
        unpack_predictions(raw, carriers, folder)
        metadata, predictions = load_submission(folder, carriers)
        displayed = {key: metadata.get(key) for key in ("reader", "version", "license")}
        if not all(text(displayed[key], size) for key, size in (("reader", 80), ("version", 60), ("license", 80))):
            raise ValueError("Use short public reader, version and licence labels.")
        if any(metadata[key] != receipt[key] for key in ("reader", "version", "license", "weights")):
            raise ValueError("The receipt and ZIP metadata must agree.")
        scored = score_submission(carriers, (metadata, predictions))
    identifier = sha256(raw).hexdigest()
    return {
        "id": identifier, "category": "C1", "reader": displayed["reader"], "version": displayed["version"],
        "type": receipt["reader_type"], "licence": displayed["license"], "date": datetime.now(timezone.utc).date().isoformat(),
        "scorer_version": scorer_version, "verified": False, "submission_sha256": identifier,
        "views": {
            view: {
                stratum: {key: scored["views"][view][stratum].get(key, 0) for key in ("edits", "chars")}
                for stratum in STRATA
            } for view in VIEWS
        },
    }


def score_registered_upload(raw, receipt):
    from heocr_bench.data import load_submission
    from heocr_bench.scoring import score_submission

    expected = os.environ["HEOCR_SCORER_COMMIT"]
    version = scorer_identity(expected)
    return score_zip(raw, receipt, benchmark_carriers(), load_submission, score_submission, version)
