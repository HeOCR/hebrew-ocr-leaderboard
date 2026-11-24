# How to submit an OCR run

1. Run your reader on the public [P-mod-open v0 benchmark](https://huggingface.co/datasets/HeOCR/p-mod-open-v0).
   Create a flat [heocr-bench ZIP](https://github.com/HeOCR/heocr-bench/tree/39ed8dddd37d9088edb72308c6f4497d6c627e2a)
   with `metadata.json` and one UTF-8 `<carrier-id>.txt` for each of the 65 carriers.
   Use an empty file for a blank result. ZIP metadata includes `reader`, `version`,
   `license`, `weights` (`open` or `closed`) and a `params` object.
2. Open a pull request into `main`, adding just `submissions/<id>.zip` and
   `submissions/<id>.json`. Use a lowercase ID with letters, digits, and hyphens.
   The JSON receipt identifies the ZIP and links to the reader's public weights,
   source, or documentation. For example:

   ```json
   {
     "sha256": "<64 lowercase hex characters>",
     "reader": "Example OCR",
     "version": "1.0.0",
     "license": "Apache-2.0",
     "weights": "open",
     "link": "https://example.org/ocr"
   }
   ```

   The four reader fields must exactly match the ZIP metadata. For an API, add
   `"reader_type": "API"`. To host the ZIP in a public Hugging Face dataset
   instead, add `"hf_url": "https://huggingface.co/datasets/ORG/REPO/resolve/COMMIT/path/predictions.zip"`
   to the receipt and add only the JSON file. Use an exact commit SHA, and check for private
   information and secrets before posting. The ZIP limit is 2 MB compressed,
   512 KB expanded, with a maximum of 32 KiB per file.
3. GitHub Actions comments on a successful score for the current PR head.
   Check the score and workflow artifact before asking the HeOCR lead to review.
   The lead decides whether to merge. One submission per reader and version is
   accepted, ignoring case and spacing. A published row is marked
   **self-submitted, unverified** until HeOCR independently reruns and reviews it.

The score uses the 65 public v0 carriers, including the nine artwork-masked
versions, and reports both registered CER views. The v0 reference texts are public.

## Maintainer review

Require the passing score comment or artifact for the **current PR head**.
Check that the declared reader/version/licence, public reader link and
prediction text are suitable for public release. Re-score if the head moved
or a competing submission for the same reader/version merged. To retry an
eligible PR, dispatch **Score submission PR** from main with its number and
exact head SHA. Only the lead merges submission PRs. GitHub Actions updates
the aggregate after merge, preserving the unverified status.

### Publishing mirrors

The existing **Sync merged leaderboard results** workflow reconciles main.
Set `HEOCR_SITE_BUILDER_COMMIT` to a merged commit of `HeOCR/heocr.github.io`
with the current builder. The optional mirror steps use
`HEOCR_ENABLE_LEADERBOARD_SYNC=1` and the
`HEOCR_LEADERBOARD_SITE_TOKEN` and `HEOCR_LEADERBOARD_HF_TOKEN` repository
secrets. Sync uses the same results bytes for the HF results dataset, static
Space and generated site PR. The site PR still needs lead review and merge.
