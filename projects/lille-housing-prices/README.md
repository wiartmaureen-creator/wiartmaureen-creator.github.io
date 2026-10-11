# What drives housing prices in the Lille metropolitan area?

**Is this price in line with the market?** An analysis in R of every recorded sale of a flat or a house
in the 95 communes of the Métropole Européenne de Lille, 2021-2025, from the public DVF records.

➡️ **Report:** [`report/lille_housing.html`](report/lille_housing.html) (R Markdown, self-contained) · **Case study:** [`index.html`](index.html)

## Key results

| | |
|---|---|
| Sales analysed | 76,047 single-dwelling sales (from 553,756 DVF rows) |
| Median price per m², 2025 | flats €3,084 · houses €2,509 |
| Quality-adjusted price index | 2021 = 100 → 2022: 104.6 → 2024: 98.1 → 2025: 100.4 |
| Most / least expensive (2024-2025, ≥150 sales) | Bondues €3,947/m², Marcq-en-Barœul €3,689 · Tourcoing €1,768, Roubaix €1,561 |
| Valuation model | R² 0.63; median error ±20.8% on unseen sales; 8.7% of sales more than 50% above the estimate |

**What it means.** Comparable homes lost about 6% between 2022 and 2024 as interest rates rose, then
recovered to their 2021 level in 2025; raw medians hide part of this because the mix of homes sold
changed. Location dominates: the same 60 m² flat is estimated at about €196k in Lille and €95k in
Roubaix. The valuation model is good enough to **screen** sales, for example to send a mortgage file
to a full appraisal, or to flag a purchase far above or below market value, a classic money-laundering
red flag in real estate. It is not precise enough to value one specific home (DVF has no information
on condition, floor or energy rating).

## Method

1. **`R/01_prepare_data.R`**: downloads the DVF files for the Nord department (2021-2025), keeps sales
   (`nature_mutation == "Vente"`) in the 95 MEL communes (list from `geo.api.gouv.fr`), keeps sales of
   exactly one dwelling so the price per m² is meaningful, and removes implausible values.
2. **`R/02_analysis.R`**: yearly medians; commune ranking; a **hedonic regression**
   `log(price_m2) ~ year + type + log(surface) + rooms + commune` whose year coefficients form a
   quality-adjusted price index; a **valuation model**
   `log(price) ~ log(surface) * type + rooms + commune + quarter` fitted on 80% of sales and tested on
   the other 20%; figures with ggplot2; `results/summary.json` for the web page.
3. **`report/lille_housing.Rmd`**: the narrative report, rendered to HTML.

Packages: dplyr, readr, tidyr, ggplot2, scales, broom, jsonlite, rmarkdown.

## Run it

```r
install.packages(c("dplyr", "readr", "tidyr", "ggplot2", "scales", "broom", "jsonlite", "rmarkdown"))
source("R/01_prepare_data.R")   # downloads the raw files if missing (about 15 MB)
source("R/02_analysis.R")
rmarkdown::render("report/lille_housing.Rmd", knit_root_dir = getwd())
```

Run from the project folder. Rendering the report needs pandoc (bundled with RStudio).

## Data and licence

*Demandes de valeurs foncières géolocalisées*, Etalab / DGFiP, published under the Licence Ouverte 2.0
(open licence). The raw files are not stored in this repository; the script downloads them. The cleaned
dataset is in `data/processed/mel_sales.csv.gz`.
