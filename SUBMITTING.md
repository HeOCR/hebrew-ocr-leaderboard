# Submit a prediction run

1. Run your reader on the public [P-mod-open v0 benchmark](https://huggingface.co/datasets/HeOCR/p-mod-open-v0).
   Make a flat ZIP in the [heocr-bench submission format](https://github.com/HeOCR/heocr-bench/tree/39ed8dddd37d9088edb72308c6f4497d6c627e2a).
   Include `metadata.json` and exactly one UTF-8 text file per carrier.
   Use public reader/version/licence labels and check the predictions for
   personal information or credentials before posting.
2. Make a PR adding `submissions/<id>.json`, with a unique lowercase
   letters/digits/hyphen ID. Include a matching `submissions/<id>.zip`,
   or put the ZIP in a public Hugging Face dataset and add an `hf_url`
   pointing to its exact commit (no branch or temporary signing URL).
3. Give the ZIP SHA-256 and reader type in the receipt. For example,

   ```json
   {
     "sha256": "<64 lowercase hex characters>",
     "reader_type": "open weights"
   }
   ```

   Hosted ZIPs also use
   `"hf_url": "https://huggingface.co/datasets/ORG/REPO/resolve/COMMIT/path/predictions.zip"`.
   Use `"API"` for a hosted API reader. The ZIP limit is 2 MB compressed,
   512 KB expanded, with a maximum of 32 KiB per file.
4. A maintainer dispatches **Score submission PR** on GitHub Actions
   using your PR number and exact head SHA. The workflow posts an aggregate
   score artifact. After the PR merges, the merge workflow scores any new
   ZIP and syncs the board. Your entry stays unverified until the maintainers
   independently rerun your reader and review the result.

For maintainers, require the passing exact-head artifact before merging
the packet. Review data privacy, public labels and licence declarations in
the PR. Accept one immutable packet per PR. Once published, the ZIP
contents and hosted predictions are held to the project’s public data rules.
