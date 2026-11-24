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


SCORER = "39ed8dddd37d9088edb72308c6f4497d6c627e2a"
READER = {"reader": "Fixture OCR", "version": "1", "license": "CC0-1.0", "weights": "open"}
CARRIERS = {"toy": Carrier("toy", "p1", "scanner", ["abc", "xyz"], [True, False])}


def fixture_receipt(raw, **fields):
    return {**READER, "link": "https://example.org/fixture", "sha256": sha256(raw).hexdigest(), **fields}


def fixture_zip(extra=None, result="abd\nxzz\n", **metadata):
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("metadata.json", json.dumps({
            **READER, "params": {}, **metadata,
        }))
        archive.writestr("toy.txt", result)
        if extra:
            archive.writestr(extra, "fixture")
    return buffer.getvalue()


class ScoreTest(unittest.TestCase):
    def test_pinned_scorer_and_unverified_aggregate(self):
        version = scorer_identity(SCORER)
        raw = fixture_zip()
        receipt = review.packet(json.dumps(fixture_receipt(raw)).encode())
        row = score_zip(raw, receipt, CARRIERS, load_submission, score_submission, version)
        self.assertEqual(row["views"]["all"]["pooled"], {"edits": 2, "chars": 7})
        self.assertEqual(row["views"]["filtered"]["pooled"], {"edits": 1, "chars": 3})
        self.assertEqual(row["id"], sha256(raw).hexdigest())
        self.assertIs(row["verified"], False)
        with self.assertRaises(ValueError):
            score_zip(fixture_zip("../extra.txt"), receipt, CARRIERS, load_submission, score_submission, version)

    def test_receipt_requires_link_and_matching_zip_metadata(self):
        raw = fixture_zip()
        missing = fixture_receipt(raw)
        del missing["link"]
        with self.assertRaisesRegex(ValueError, "receipt fields"):
            review.packet(json.dumps(missing).encode())
        receipt = review.packet(json.dumps(fixture_receipt(raw, weights="closed")).encode())
        self.assertEqual(receipt["reader_type"], "closed weights")
        with self.assertRaisesRegex(ValueError, "must agree"):
            score_zip(raw, receipt, CARRIERS, load_submission, score_submission, scorer_identity(SCORER))

    def test_hf_links_and_digest(self):
        pin = "9" * 40
        url = f"https://huggingface.co/datasets/Open/team/resolve/{pin}/predictions.zip"
        self.assertIsNotNone(review.HF_LINK.fullmatch(url))
        for unsafe in (url + "?x=1", url.replace(pin, "main"), url.replace("huggingface.co", "example.org")):
            with self.assertRaises(ValueError):
                review.fetch_hf(unsafe)
        with self.assertRaises(ValueError):
            review.HFRedirects().redirect_request(None, None, 302, "", {}, "http://huggingface.co/file")
        expected = fixture_receipt(b"data", hf_url=url, reader_type="API")
        with patch("review.fetch_hf", return_value=b"data"), patch("review.score_registered_upload") as scorer:
            review.score_packet(pin, expected, None)
            scorer.assert_called_once_with(b"data", expected)
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
        self.add_packet("test", self.raw, fixture_receipt(self.raw))
        self.head = review.git("rev-parse", "HEAD").decode().strip()
        review.git("update-ref", "refs/pull/1/head", self.head)

    def add_packet(self, name, raw, receipt):
        Path(f"submissions/{name}.json").write_text(json.dumps(receipt))
        Path(f"submissions/{name}.zip").write_bytes(raw)
        review.git("add", "submissions")
        review.git("commit", "-qm", f"add fixture {name}")

    def test_invented_reader_pr_comment_merge_and_reconcile(self):
        review.git("switch", "-q", "main")
        path = Path("results.json")
        before = path.read_bytes()
        with patch.dict(os.environ, {"HEOCR_SCORER_COMMIT": SCORER}), patch(
            "submissions.benchmark_carriers", return_value=CARRIERS
        ):
            with patch("sys.argv", ["review.py", "pr", "1", self.head, "out/score.json", "--comment", "out/comment.md"]):
                self.assertEqual(review.main(), 0)
            result = json.loads(Path("out/score.json").read_bytes())
            self.assertEqual(result["head_sha"], self.head)
            comment = Path("out/comment.md").read_text()
            self.assertIn(self.head, comment)
            self.assertIn("Self-submitted, unverified", comment)
            self.assertIn("| Office scanner | 33.33% | 28.57% |", comment)
            self.assertNotIn(READER["reader"], comment)
            self.assertFalse(Path("submissions/test.json").exists())
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaisesRegex(ValueError, "moved"):
                review.score_pr(1, self.base)

            review.git("merge", "--squash", "submit")
            review.git("commit", "-qm", "reviewed fixture merge")
            with patch("sys.argv", ["review.py", "reconcile", "results.json"]):
                self.assertEqual(review.main(), 0)
                first = path.read_bytes()
                self.assertEqual(review.main(), 0)
            self.assertEqual(path.read_bytes(), first)
            after = read_results(path)
            self.assertEqual(after["rows"][:-1], json.loads(before)["rows"])
            self.assertEqual(after["rows"][-1], result["row"])
            self.assertIs(after["rows"][-1]["verified"], False)

    def test_reject_reader_version_duplicates_before_and_after_reconcile(self):
        review.git("switch", "-q", "main")
        review.git("merge", "--ff-only", "submit")
        review.git("switch", "-qc", "duplicate")
        raw = fixture_zip(result="abc\nxyz\n", reader="fixture   ocr", version="１")
        self.add_packet("duplicate", raw, fixture_receipt(raw, reader="fixture   ocr", version="１"))
        head = review.git("rev-parse", "HEAD").decode().strip()
        review.git("update-ref", "refs/pull/2/head", head)
        review.git("switch", "-q", "main")
        with patch.dict(os.environ, {"HEOCR_SCORER_COMMIT": SCORER}), patch(
            "submissions.benchmark_carriers", return_value=CARRIERS
        ):
            with self.assertRaisesRegex(review.DuplicateSubmission, "reader and version"):
                review.score_pr(2, head)
            path = Path("results.json")
            accepted = review.reconcile(path)
            review.write_json(path, accepted)
            with self.assertRaises(review.DuplicateSubmission):
                review.score_pr(2, head)
            review.git("merge", "--ff-only", "duplicate")
            self.assertEqual(review.reconcile(path), accepted)

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



if __name__ == "__main__":
    unittest.main()
