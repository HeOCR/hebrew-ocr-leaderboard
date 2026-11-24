"""Offline tests with an invented carrier and disposable Git repositories."""

from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from heocr_bench.data import Carrier, load_submission
from heocr_bench.scoring import score_submission

import review
from leaderboard_results import ARTWORK_MASK_NOTICE, BIAS_NOTICE, ranked, read_results, validate
from submissions import score_zip, scorer_identity


def fixture_zip(extra=None):
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("metadata.json", json.dumps({
            "reader": "Fixture", "version": "1", "license": "CC0-1.0", "weights": "open", "params": {},
        }))
        archive.writestr("toy.txt", "abd\nxzz\n")
        if extra:
            archive.writestr(extra, "fixture")
    return buffer.getvalue()


class ScoreTest(unittest.TestCase):
    def test_pinned_scorer_and_unverified_aggregate(self):
        version = scorer_identity("39ed8dddd37d9088edb72308c6f4497d6c627e2a")
        roster = {"toy": Carrier("toy", "p1", "scanner", ["abc", "xyz"], [True, False])}
        raw = fixture_zip()
        row = score_zip(raw, "open weights", roster, load_submission, score_submission, version)
        self.assertEqual(row["views"]["all"]["pooled"], {"edits": 2, "chars": 7})
        self.assertEqual(row["views"]["filtered"]["pooled"], {"edits": 1, "chars": 3})
        self.assertEqual(row["id"], sha256(raw).hexdigest())
        self.assertIs(row["verified"], False)
        with self.assertRaises(ValueError):
            score_zip(fixture_zip("../extra.txt"), "open weights", roster, load_submission, score_submission, version)

    def test_hf_links_and_digest(self):
        pin = "9" * 40
        url = f"https://huggingface.co/datasets/Open/team/resolve/{pin}/predictions.zip"
        self.assertIsNotNone(review.HF_LINK.fullmatch(url))
        for unsafe in (url + "?x=1", url.replace(pin, "main"), url.replace("huggingface.co", "example.org")):
            with self.assertRaises(ValueError):
                review.fetch_hf(unsafe)
        with self.assertRaises(ValueError):
            review.HFRedirects().redirect_request(None, None, 302, "", {}, "http://huggingface.co/file")
        expected = {"hf_url": url, "sha256": sha256(b"data").hexdigest(), "reader_type": "API"}
        with patch("review.fetch_hf", return_value=b"data"), patch("review.score_registered_upload") as scorer:
            review.score_packet(pin, expected, None)
            scorer.assert_called_once_with(b"data", "API")
        with patch("review.fetch_hf", return_value=b"other"), self.assertRaisesRegex(ValueError, "SHA-256"):
            review.score_packet(pin, expected, None)


class DiagnosticTest(unittest.TestCase):
    def test_api_diagnostics_keep_both_scopes_outside_rankings(self):
        data = read_results(Path(__file__).with_name("results.json"))
        diagnostics = {
            "google-vision-document-text-v0": (10007, 1268),
            "google-document-ai-ocr-v21-v0": (11297, 1364),
            "claude-haiku-5-5-v0": (5107, 429),
        }
        rows = {row["id"]: row for row in data["rows"]}
        for key, (paired, masked) in diagnostics.items():
            with self.subTest(reader=key):
                row = rows[key]
                detail = row["diagnostic"]
                self.assertEqual(row["type"], "commercial API")
                self.assertEqual(detail["notice"], ARTWORK_MASK_NOTICE)
                self.assertEqual(row["views"]["filtered"]["pooled"], {"edits": paired, "chars": 61212})
                self.assertEqual(detail["masked_views"]["filtered"]["pooled"], {"edits": masked, "chars": 9333})
        baseline = {**data, "rows": [row for row in data["rows"] if row["id"] not in diagnostics]}
        for view in ("all", "filtered"):
            self.assertEqual(ranked(data, view), ranked(baseline, view))
        self.assertEqual(rows["gemini-vertex-v0"]["diagnostic"]["notice"], BIAS_NOTICE)

    def test_haiku45_requires_an_output_cap_disclosure(self):
        data = read_results(Path(__file__).with_name("results.json"))
        row = next(row for row in data["rows"] if row["id"] == "claude-haiku-4-5-v0")
        self.assertEqual(
            row["diagnostic"]["notice"],
            ARTWORK_MASK_NOTICE
            + " 64/65 Haiku 4.5 replies were Hebrew-dominant (median 100% Hebrew letters), 1 Latin-dominant."
            " 11 hit the output cap.",
        )
        for view in ("all", "filtered"):
            self.assertNotIn(row, ranked(data, view))
        row["diagnostic"]["notice"] = ARTWORK_MASK_NOTICE
        with self.assertRaisesRegex(ValueError, "Invalid diagnostic breakdown"):
            validate(data)

    def test_new_api_diagnostic_cannot_use_the_bias_notice(self):
        data = read_results(Path(__file__).with_name("results.json"))
        vision = next(row for row in data["rows"] if row["id"] == "google-vision-document-text-v0")
        vision["diagnostic"]["notice"] = BIAS_NOTICE
        with self.assertRaisesRegex(ValueError, "Invalid diagnostic breakdown"):
            validate(data)


class GitPacketTest(unittest.TestCase):
    def setUp(self):
        root = Path(temp := self.enterContext(TemporaryDirectory()))
        baseline = Path(__file__).parent / "results.json"
        seed = baseline.read_bytes()
        cwd = Path.cwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(root)
        review.git("init", "-q", "--initial-branch=main")
        review.git("config", "user.name", "Fixture")
        review.git("config", "user.email", "fixture@example.com")
        Path("submissions").mkdir()
        Path("results.json").write_bytes(seed)
        review.git("add", ".")
        review.git("commit", "-qm", "base")
        self.base = review.git("rev-parse", "HEAD").decode().strip()
        review.git("remote", "add", "origin", temp)
        review.git("switch", "-qc", "submit")
        self.raw = fixture_zip()
        self.digest = sha256(self.raw).hexdigest()
        Path("submissions/test.json").write_text(json.dumps({"sha256": self.digest, "reader_type": "open weights"}))
        Path("submissions/test.zip").write_bytes(self.raw)
        review.git("add", ".")
        review.git("commit", "-qm", "add a fixture")
        self.head = review.git("rev-parse", "HEAD").decode().strip()
        review.git("update-ref", "refs/pull/1/head", self.head)

    def test_only_reads_new_packet_from_pinned_head(self):
        review.git("switch", "-q", "main")
        with patch("review.score_registered_upload", return_value={"id": self.digest}) as scorer:
            result = review.score_pr(1, self.head)
            scorer.assert_called_once_with(self.raw, "open weights")
        self.assertEqual(result, {"pull_request": 1, "head_sha": self.head, "row": {"id": self.digest}})
        self.assertFalse(Path("submissions/test.json").exists())
        with self.assertRaisesRegex(ValueError, "moved"):
            review.score_pr(1, self.base)

    def test_unrelated_files_and_nonregular_zip_are_rejected(self):
        Path("workflow.sh").write_text("fixture")
        review.git("add", ".")
        review.git("commit", "-qm", "unrelated")
        review.git("update-ref", "refs/pull/1/head", "HEAD")
        head = review.git("rev-parse", "HEAD").decode().strip()
        review.git("switch", "-q", "main")
        with self.assertRaisesRegex(ValueError, "only add one"):
            review.score_pr(1, head)
        review.git("switch", "-q", "submit")
        path = Path("submissions/test.zip")
        path.unlink()
        path.symlink_to("../workflow.sh")
        review.git("add", ".")
        review.git("commit", "-qm", "nonregular ZIP")
        head = review.git("rev-parse", "HEAD").decode().strip()
        with self.assertRaisesRegex(ValueError, "ordinary"):
            review.read_blob(head, path.as_posix(), 2_000_000)

    def test_reconcile_scores_once_and_keeps_seed(self):
        path = Path("results.json")
        current = review.read_results(path)
        metrics = current["rows"][0]["views"]
        row = dict(current["rows"][0], id=self.digest, type="open weights", views=metrics,
                   submission_sha256=self.digest, verified=False)
        with patch("review.score_registered_upload", return_value=row) as scorer:
            merged = review.reconcile(path)
            review.write_json(path, merged)
            self.assertEqual(review.reconcile(path), merged)
            scorer.assert_called_once_with(self.raw, "open weights")
        self.assertEqual(merged["rows"], [*current["rows"], row])


if __name__ == "__main__":
    unittest.main()
