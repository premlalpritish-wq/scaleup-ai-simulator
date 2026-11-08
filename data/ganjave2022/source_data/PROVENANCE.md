# Source data provenance — `data/ganjave2022/source_data/`

Everything recovered from Ganjave et al. (2022), and how it got here. Nothing in this
directory feeds the frozen evaluation.

## Chain

```
papers/Ganjave et al 2022.pdf  (article, doi:10.1016/j.btre.2021.e00694)
        |  no data-availability statement, no repository named
        v
PMC8718739  "Appendix. Supplementary materials"  ->  mmc1.docx (2.1 MB)
        |  retrieved via Europe PMC REST
        |  https://www.ebi.ac.uk/europepmc/webservices/rest/PMC8718739/supplementaryFiles
        v
PMC8718739_supplementary.zip  (3,071,054 bytes, 16 parts)
        |
        +-- mmc1_supplementary.docx ....... OOXML, inspected part by part
        |     |
        |     +-- word/document.xml ....... 3 tables, 44 paragraphs   -> supplementary_inventory.json
        |     +-- word/charts/chart1.xml .. kLa plot, 0 cached points -> supplementary_charts.json
        |     +-- word/charts/chart2.xml .. kLa plot, 0 cached points -> supplementary_charts.json
        |     +-- word/media/* ............ 11 images, no numeric data
        |
        +-- gr3.jpg ....................... main-text Figure 3, 750x512
                                          (LOWER resolution than the PDF-embedded
                                           images the digitisation already used)
        v
recovered_numerical_data.json ....... Table S4, 24 kLa measurements, normalised
```

## Integrity hashes (SHA-256)

| File | Bytes | SHA-256 |
|---|---|---|
| `PMC8718739_supplementary.zip` | 3,071,054 | `f50c75b00f2dbcfeb55290f2534c854aae9580917baac71ce11615d020374e57` |
| `mmc1_supplementary.docx` | 2,192,379 | `2b24a4fd43bf4e94e7a8f30da4c59ae298fc3d512b3b919e51a9de2049b29ee1` |
| `gr3_maintext_fig3.jpg` | 99,174 | `ff45d6279d75ea4ec7cf6dcdf030b31afdbedcfd7d9e4a4c85c2ff9040302ed8` |
| `chart1.xml` | 5,554 | `e0b6a21f3b95c0ee75eb3deed268ec23959c57ea7d4306852e38ccd5c7aa5460` |
| `chart2.xml` | 6,195 | `420751868610b2c30e2d86027538962a361e7e242c2424038b86d2d112e75b7a` |

The two package hashes are also embedded in `recovered_numerical_data.json`, so the
normalised record carries the identity of the files it was derived from.

## Licensing

The article is **CC BY-NC-ND 4.0**
(http://creativecommons.org/licenses/by-nc-nd/4.0/), as stated on the PMC and publisher
pages.

- The publisher's files are stored **unmodified**, with attribution to the article.
- No derivative of them is redistributed. `recovered_numerical_data.json` restates
  numerical values for analysis; that is a derived work about the data, not a
  redistribution of the publisher's document.
- Anyone redistributing `mmc1_supplementary.docx` or the ZIP must preserve the CC
  BY-NC-ND terms, including NoDerivatives.

## Data classification

Every record in `recovered_numerical_data.json` carries:

```
"data_class": "author_reported_measurement",
"digitized": false,
"reading_uncertainty": null
```

This is deliberate and is the distinction the recovery turns on. The frozen evaluation's
observations are `digitized: true` with a `reading_uncertainty`, because a program in this
repository read them off a raster figure. The recovered Table S4 values are numbers the
authors wrote down, so they carry no reading uncertainty — **and no time course**.

**A figure-digitised coordinate must never be recorded as an author's original numerical
data.** Nothing here does, and `composition/tests/test_source_data_recovery.py` asserts it.

## Transformations applied to Table S4

Exactly two, both flagged per record:

1. **`merged_cell_forward_fill`** — Word vertical merges leave the volume and RPM cells
   blank on continuation rows; a blank means *same as above*, not *missing*. Flagged by
   `volume_forward_filled` and `rpm_forward_filled`.
2. **`column_group_assignment`** — the left block is the 2.5 cm pitch series and the
   right block the 5 cm pitch series, per the table caption. Recorded as `pitch_cm`.

Not applied: no smoothing, fitting, interpolation, unit conversion, averaging, or
imputation of any kind.

## What was searched and not found

See `search_log.json` for all eleven steps. Summary: no data-availability statement, no
repository deposit, no spreadsheet or CSV anywhere in the package, no cached chart
values, and no dataset link in PMC or Europe PMC metadata. The supplementary contains no
Figure 3a/3b time course, and Figure 3 is not repeated there at higher resolution.

## Relationship to the frozen evaluation

**None. This directory is read-only with respect to `data/ganjave2022/`'s frozen files.**

The five frozen inputs — `frozen_configuration.json`, `observations.json`,
`evaluation_protocol.json`, `figure_reference_data.json`, `reference_parameters.json` —
are unchanged, verified by digest before and after this recovery. The primary evaluation
still reports `fail` with RMSE 2.5204 g/L.

A future recovery of the actual time courses gets its own dataset, its own protocol and
its own report. It must not be merged into `observations.json`, which is the
figure-digitised dataset the failed evaluation used.
