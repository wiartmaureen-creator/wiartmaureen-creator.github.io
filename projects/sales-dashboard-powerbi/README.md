# Management reporting dashboard in Power BI

**The monthly report says sales are on budget. Are we making the margin we planned, and if not, where should we act?**

A Power BI reporting dashboard for a fictitious retail chain (11 garden centres + an online
shop): star-schema model, 21 DAX measures, three report pages. It shows that 2025 sales are
on budget (+0.4%) while gross margin is **€457k behind**, and traces the gap to decisions
management can take.

➡️ **Case study with a live web version of the dashboard:** [`index.html`](index.html)

## Findings and decisions

| Finding | At stake | Decision |
|---|---|---|
| Summer barbecue promotion: units +23%, sales +4%, margin rate 33.6% → 21.2% | −€481k margin | Target end-of-season stock instead of a blanket 22% discount |
| Metz store: −19% since a competitor opened in April, −18% vs budget over the year | −€682k vs budget | Local plan and reforecast; review the site if no recovery in two quarters |
| Online shop +40%, but 9% of furniture sold online is returned (stores: 1.2%) | €133k returns | Better product pages, review the return policy |
| Outdoor lighting +29% vs 2024, +11% vs budget | +€0.7M | More space and range in 2026 |

## The model

```
            dim_date (marked date table)
               │             │
fact_sales ────┤             ├──── fact_budget (month grain, joined on month start)
  day × store × category     │       month × store × category
               │             │
            dim_store     dim_category
```

Measures (display folders *Sales*, *Margin*, *Budget*): Net Sales, Gross Sales, Total Discount,
Total Returns, Units Sold, Net Sales LY, Net Sales YoY %, Units YoY %, Cost of Sales,
Gross Margin, Gross Margin %, Gross Margin LY, Gross Margin % LY, Gross Margin % Change (pts),
Discount Rate, Return Rate, Budget, Budget Gross Margin, Net Sales vs Budget,
Net Sales vs Budget %, Gross Margin vs Budget.

Report pages: **Overview** (KPI cards, monthly trend vs last year and budget, growth by
category, store table), **Margin & promotions** (discount rate vs margin rate by month, margin
change by category), **Stores vs budget** (variance by store, monthly trend, detail table).
A report-level filter shows 2025; last year comes from the measures.

## How it was built and tested

The project is saved as **PBIP** (the text format of a .pbix): the model in TMDL, the report in
PBIR. `src/build_pbip.py` writes both, then:

1. validates the 40 report JSON files against Microsoft's published schemas (0 problems);
2. the model was deployed to the Power BI engine with Microsoft's Tabular Object Model, refreshed
   from the CSV files, and every headline measure was queried in DAX (`results/dax_check.json`):
   the figures match the independent pandas calculation in `src/analyse.py` to the cent;
3. the project opens and refreshes in Power BI Desktop (2.158): the screenshots in `images/` come from it.

## Open it

1. Open `powerbi/CalyxReporting.pbip` in Power BI Desktop.
2. If the files are not where the project expects them, set the **DataFolder** parameter
   (*Transform data > Edit parameters*) to the full path of the `data` folder, ending with `\`.
3. Click **Refresh**.

To regenerate everything:

```bash
python src/generate_sales_data.py   # data/*.csv
python src/analyse.py               # results/summary.json, results/dashboard_data.js
python src/build_pbip.py            # powerbi/ (with schema validation)
```

---
*Calyx Home & Garden is fictitious; all data is synthetic.*
