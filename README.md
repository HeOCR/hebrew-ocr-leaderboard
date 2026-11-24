# HeOCR Hebrew OCR leaderboard

Results use page character error rate on P-mod-open v0. The public v0
references can influence training and submissions. A hidden v1 split is
planned.

[Submit an OCR run](SUBMITTING.md) · [Results JSON](results.json) ·
[Benchmark scorer](https://github.com/HeOCR/heocr-bench)

`results.json` is the canonical aggregate snapshot. The same bytes are
published to the results dataset, bundled into the static Space, and given
to the bilingual site builder. Scores on the board retain the registered
view and denominator for each stratum.

## Document type and capture

The document-type view reuses saved v0 predictions, including three additional
recorded external runs. It defaults to the same 56 pixel-matched carriers
for every reader. Full-original scores use 65 original carriers where
available. Hosted artwork-masked results use nine separate diagnostic
carriers. Neither the ranked table nor its roster changes.

The [page taxonomy](c1-document-types-taxonomy.json) assigns one layout
label using the release QA record. Gazette / legal notice groups pages
by provenance and can overlap forms, tables, prose or contents. Layouts
label whole pages, so table-page scores include any accompanying prose.
Scores are micro CER with the frozen v0 masks, and each cell gives the
number of scored carriers. Phone A and Phone B also have a pooled column.
Gemini participated in constructing the v0 references.
