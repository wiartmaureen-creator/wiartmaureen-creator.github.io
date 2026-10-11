"""Write the Power BI project (PBIP) for the Calyx management reporting dashboard.

A PBIP is the text form of a .pbix file: the semantic model is written in TMDL
and the report in PBIR (one JSON file per page and per visual). Power BI
Desktop opens CalyxReporting.pbip directly; "Refresh" loads the CSV files.

The script:
  1. writes the semantic model: tables, columns, relationships, 21 DAX measures,
     a DataFolder parameter pointing at data/;
  2. writes three report pages (Overview, Margin & promotions, Stores vs budget);
  3. validates every report JSON file against Microsoft's published schemas.

Usage:
    python src/build_pbip.py [--no-validate]
"""

from __future__ import annotations

import json
import shutil
import sys
import uuid
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
PBIP_DIR = PROJECT_DIR / "powerbi"
NAME = "CalyxReporting"
MODEL_DIR = PBIP_DIR / f"{NAME}.SemanticModel"
REPORT_DIR = PBIP_DIR / f"{NAME}.Report"

SCHEMA_ROOT = "https://developer.microsoft.com/json-schemas/fabric"
SCHEMAS = {
    "pbip": f"{SCHEMA_ROOT}/pbip/pbipProperties/1.0.0/schema.json",
    "pbism": f"{SCHEMA_ROOT}/item/semanticModel/definitionProperties/1.0.0/schema.json",
    "pbir": f"{SCHEMA_ROOT}/item/report/definitionProperties/2.0.0/schema.json",
    "version": f"{SCHEMA_ROOT}/item/report/definition/versionMetadata/1.0.0/schema.json",
    "report": f"{SCHEMA_ROOT}/item/report/definition/report/3.0.0/schema.json",
    "pages": f"{SCHEMA_ROOT}/item/report/definition/pagesMetadata/1.0.0/schema.json",
    "page": f"{SCHEMA_ROOT}/item/report/definition/page/2.0.0/schema.json",
    "visual": f"{SCHEMA_ROOT}/item/report/definition/visualContainer/2.2.0/schema.json",
}

PAGE_WIDTH, PAGE_HEIGHT = 1280, 720
TAB = "\t"


def tag(*parts: str) -> str:
    """Deterministic lineage tag, so rebuilding does not churn the files."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "calyx/" + "/".join(parts)))


# --- Semantic model ---------------------------------------------------------------

# table -> (csv file, [(column, tmdl type, M type, summarise by, format string)])
TABLES = {
    "dim_date": ("dim_date.csv", [
        ("date", "dateTime", "type date", "none", "Short Date"),
        ("year", "int64", "Int64.Type", "none", "0"),
        ("quarter", "string", "type text", "none", None),
        ("month_number", "int64", "Int64.Type", "none", "0"),
        ("month", "string", "type text", "none", None),
        ("year_month", "string", "type text", "none", None),
        ("weekday", "string", "type text", "none", None),
        ("is_weekend", "int64", "Int64.Type", "none", "0"),
    ]),
    "dim_store": ("dim_store.csv", [
        ("store_id", "string", "type text", "none", None),
        ("store_name", "string", "type text", "none", None),
        ("region", "string", "type text", "none", None),
        ("channel", "string", "type text", "none", None),
        ("opened", "int64", "Int64.Type", "none", "0"),
        ("surface_m2", "int64", "Int64.Type", "sum", "#,0"),
    ]),
    "dim_category": ("dim_category.csv", [
        ("category_id", "string", "type text", "none", None),
        ("category", "string", "type text", "none", None),
    ]),
    "fact_sales": ("fact_sales.csv", [
        ("date", "dateTime", "type date", "none", "Short Date"),
        ("store_id", "string", "type text", "none", None),
        ("category_id", "string", "type text", "none", None),
        ("units", "int64", "Int64.Type", "sum", "#,0"),
        ("gross_sales", "double", "type number", "sum", "#,0"),
        ("discount", "double", "type number", "sum", "#,0"),
        ("returns", "double", "type number", "sum", "#,0"),
        ("net_sales", "double", "type number", "sum", "#,0"),
        ("cost_of_sales", "double", "type number", "sum", "#,0"),
    ]),
    "fact_budget": ("fact_budget.csv", [
        ("month_start", "dateTime", "type date", "none", "Short Date"),
        ("store_id", "string", "type text", "none", None),
        ("category_id", "string", "type text", "none", None),
        ("budget_net_sales", "double", "type number", "sum", "#,0"),
        ("budget_gross_margin", "double", "type number", "sum", "#,0"),
    ]),
}

RELATIONSHIPS = [
    ("fact_sales", "date", "dim_date", "date"),
    ("fact_sales", "store_id", "dim_store", "store_id"),
    ("fact_sales", "category_id", "dim_category", "category_id"),
    ("fact_budget", "month_start", "dim_date", "date"),
    ("fact_budget", "store_id", "dim_store", "store_id"),
    ("fact_budget", "category_id", "dim_category", "category_id"),
]

# (name, DAX, format string, display folder) - all measures live on fact_sales.
MEASURES = [
    ("Net Sales", "SUM(fact_sales[net_sales])", "#,0", "Sales"),
    ("Gross Sales", "SUM(fact_sales[gross_sales])", "#,0", "Sales"),
    ("Total Discount", "SUM(fact_sales[discount])", "#,0", "Sales"),
    ("Total Returns", "SUM(fact_sales[returns])", "#,0", "Sales"),
    ("Units Sold", "SUM(fact_sales[units])", "#,0", "Sales"),
    ("Net Sales LY", "CALCULATE([Net Sales], SAMEPERIODLASTYEAR(dim_date[date]))", "#,0", "Sales"),
    ("Net Sales YoY %", "VAR LastYear = [Net Sales LY]\nRETURN DIVIDE([Net Sales] - LastYear, LastYear)", "0.0%", "Sales"),
    ("Units YoY %", "VAR LastYear = CALCULATE([Units Sold], SAMEPERIODLASTYEAR(dim_date[date]))\n"
                    "RETURN DIVIDE([Units Sold] - LastYear, LastYear)", "0.0%", "Sales"),
    ("Cost of Sales", "SUM(fact_sales[cost_of_sales])", "#,0", "Margin"),
    ("Gross Margin", "[Net Sales] - [Cost of Sales]", "#,0", "Margin"),
    ("Gross Margin %", "DIVIDE([Gross Margin], [Net Sales])", "0.0%", "Margin"),
    ("Gross Margin LY", "CALCULATE([Gross Margin], SAMEPERIODLASTYEAR(dim_date[date]))", "#,0", "Margin"),
    ("Gross Margin % LY", "CALCULATE([Gross Margin %], SAMEPERIODLASTYEAR(dim_date[date]))", "0.0%", "Margin"),
    ("Gross Margin % Change (pts)", "([Gross Margin %] - [Gross Margin % LY]) * 100", "+0.0;-0.0;0.0", "Margin"),
    ("Discount Rate", "DIVIDE([Total Discount], [Gross Sales])", "0.0%", "Margin"),
    ("Return Rate", "DIVIDE([Total Returns], [Gross Sales] - [Total Discount])", "0.0%", "Margin"),
    ("Budget", "SUM(fact_budget[budget_net_sales])", "#,0", "Budget"),
    ("Budget Gross Margin", "SUM(fact_budget[budget_gross_margin])", "#,0", "Budget"),
    ("Net Sales vs Budget", "[Net Sales] - [Budget]", "+#,0;-#,0;0", "Budget"),
    ("Net Sales vs Budget %", "DIVIDE([Net Sales vs Budget], [Budget])", "+0.0%;-0.0%;0.0%", "Budget"),
    ("Gross Margin vs Budget", "[Gross Margin] - [Budget Gross Margin]", "+#,0;-#,0;0", "Budget"),
]


def quote(name: str) -> str:
    return f"'{name}'" if any(c in name for c in " %().-") else name


def indent_block(text: str, level: int) -> str:
    return "\n".join(TAB * level + line for line in text.splitlines())


def m_partition(table: str, file_name: str, columns) -> str:
    types = ", ".join(f'{{"{c}", {m_type}}}' for c, _, m_type, _, _ in columns)
    return (
        "let\n"
        f'    Source = Csv.Document(File.Contents(DataFolder & "{file_name}"), '
        f"[Delimiter = \",\", Columns = {len(columns)}, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),\n"
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),\n"
        f'    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")\n'
        "in\n"
        "    Typed"
    )


def table_tmdl(table: str) -> str:
    file_name, columns = TABLES[table]
    lines = [f"table {table}", f"{TAB}lineageTag: {tag(table)}"]
    if table == "dim_date":
        lines.append(f"{TAB}dataCategory: Time")
    lines.append("")
    if table == "fact_sales":
        for name, dax, fmt, folder in MEASURES:
            if "\n" in dax:
                lines.append(f"{TAB}measure {quote(name)} =")
                lines.append(indent_block(dax, 3))
            else:
                lines.append(f"{TAB}measure {quote(name)} = {dax}")
            lines.append(f"{TAB * 2}formatString: {fmt}")
            lines.append(f"{TAB * 2}displayFolder: {folder}")
            lines.append(f"{TAB * 2}lineageTag: {tag(table, 'measure', name)}")
            lines.append("")
    for name, data_type, _, summarize, fmt in columns:
        lines.append(f"{TAB}column {quote(name)}")
        lines.append(f"{TAB * 2}dataType: {data_type}")
        if fmt:
            lines.append(f"{TAB * 2}formatString: {fmt}")
        if table == "dim_date" and name == "date":
            lines.append(f"{TAB * 2}isKey")
        lines.append(f"{TAB * 2}lineageTag: {tag(table, name)}")
        lines.append(f"{TAB * 2}summarizeBy: {summarize}")
        lines.append(f"{TAB * 2}sourceColumn: {name}")
        if table == "dim_date" and name == "month":
            lines.append(f"{TAB * 2}sortByColumn: month_number")
        if name.endswith("_id") or (table.startswith("fact") and name in ("date", "month_start")):
            lines.append(f"{TAB * 2}isHidden")
        lines.append("")
        lines.append(f"{TAB * 2}annotation SummarizationSetBy = Automatic")
        if data_type == "dateTime":
            lines.append("")
            lines.append(f"{TAB * 2}annotation UnderlyingDateTimeDataType = Date")
        lines.append("")
    lines.append(f"{TAB}partition {table} = m")
    lines.append(f"{TAB * 2}mode: import")
    lines.append(f"{TAB * 2}source =")
    lines.append(indent_block(m_partition(table, file_name, columns), 4))
    lines.append("")
    lines.append(f"{TAB}annotation PBI_ResultType = Table")
    lines.append("")
    return "\n".join(lines)


def check_names():
    """A measure cannot share its name with a column of its table (names are case-insensitive)."""
    columns = {c[0].lower() for c in TABLES["fact_sales"][1]}
    clashes = [m[0] for m in MEASURES if m[0].lower() in columns]
    if clashes:
        raise SystemExit(f"Measure names clash with columns: {clashes}")


def write_model():
    check_names()
    definition = MODEL_DIR / "definition"
    (definition / "tables").mkdir(parents=True, exist_ok=True)
    write_json(MODEL_DIR / "definition.pbism", {"$schema": SCHEMAS["pbism"], "version": "4.2", "settings": {}})
    write_text(definition / "database.tmdl", "database\n\tcompatibilityLevel: 1600\n")
    model_lines = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        'annotation PBI_QueryOrder = ["DataFolder","dim_date","dim_store","dim_category","fact_sales","fact_budget"]',
        "",
    ] + [f"ref table {table}" for table in TABLES] + [""]
    write_text(definition / "model.tmdl", "\n".join(model_lines))
    folder = str(DATA_DIR) + "\\"  # M strings do not escape backslashes
    write_text(definition / "expressions.tmdl",
               f'expression DataFolder = "{folder}" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n'
               f"\tlineageTag: {tag('parameter', 'DataFolder')}\n\n"
               "\tannotation PBI_ResultType = Text\n")
    relationship_lines = []
    for from_table, from_column, to_table, to_column in RELATIONSHIPS:
        relationship_lines += [f"relationship {tag('rel', from_table, from_column, to_table)}",
                               f"\tfromColumn: {from_table}.{from_column}",
                               f"\ttoColumn: {to_table}.{to_column}", ""]
    write_text(definition / "relationships.tmdl", "\n".join(relationship_lines))
    for table in TABLES:
        write_text(definition / "tables" / f"{table}.tmdl", table_tmdl(table))


# --- Report -----------------------------------------------------------------------

def column(entity: str, prop: str) -> dict:
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def measure(prop: str) -> dict:
    return {"Measure": {"Expression": {"SourceRef": {"Entity": "fact_sales"}}, "Property": prop}}


# Friendly column headers in visuals (the model keeps snake_case names).
DISPLAY_NAMES = {"store_name": "Store", "category": "Category", "region": "Region",
                 "channel": "Channel", "month": "Month"}
INK, MUTED_GREY, BLUE, ORANGE = "#0B0B0B", "#898781", "#2A78D6", "#EB6834"


def projection(field: dict) -> dict:
    kind = "Column" if "Column" in field else "Measure"
    entity = field[kind]["Expression"]["SourceRef"]["Entity"]
    prop = field[kind]["Property"]
    result = {"field": field, "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if prop in DISPLAY_NAMES:
        result["displayName"] = DISPLAY_NAMES[prop]
    return result


def colour(hex_value: str) -> dict:
    return {"solid": {"color": literal(hex_value)}}


def series_colours(colours: dict) -> list:
    """dataPoint formatting: one fixed colour per measure (2025 blue, last year grey, budget orange)."""
    return [{"properties": {"fill": colour(hex_value)}, "selector": {"metadata": f"fact_sales.{name}"}}
            for name, hex_value in colours.items()]


def literal(value) -> dict:
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        text = f"{value}D"
    else:
        text = "'" + str(value).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": text}}}


def visual(name, visual_type, x, y, width, height, roles, title=None, sort=None, objects=None, z=0):
    config = {
        "visualType": visual_type,
        "query": {"queryState": {role: {"projections": [projection(f) for f in fields]}
                                 for role, fields in roles.items()}},
        "drillFilterOtherVisuals": True,
    }
    if sort:
        field, direction = sort
        config["query"]["sortDefinition"] = {"sort": [{"field": field, "direction": direction}], "isDefaultSort": False}
    if objects:
        config["objects"] = objects
    if title:
        config["visualContainerObjects"] = {
            "title": [{"properties": {"show": literal(True), "text": literal(title), "fontSize": literal(12),
                                      "bold": literal(True), "fontColor": colour(INK)}}]
        }
    return {
        "$schema": SCHEMAS["visual"],
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": width, "height": height, "tabOrder": z},
        "visual": config,
    }


def slicer(name, x, field, title, width=180):
    return visual(name, "slicer", x, 10, width, 66, {"Values": [field]}, title=title,
                  objects={"data": [{"properties": {"mode": literal("Dropdown")}}],
                           "header": [{"properties": {"show": literal(False)}}]})


def header(name, title, subtitle):
    """Page title as a text box: report name in bold, what the page answers underneath."""
    container = visual(name, "textbox", 20, 8, 640, 70, {})
    del container["visual"]["query"]
    container["visual"]["objects"] = {"general": [{"properties": {"paragraphs": [
        {"textRuns": [{"value": title, "textStyle": {"fontWeight": "bold", "fontSize": "18pt", "color": INK}}]},
        {"textRuns": [{"value": subtitle, "textStyle": {"fontSize": "11pt", "color": "#52514E"}}]},
    ]}}]}
    return container


TABLE_STYLE = {
    "columnHeaders": [{"properties": {"fontSize": literal(10), "bold": literal(True)}}],
    "values": [{"properties": {"fontSize": literal(10)}}],
    "total": [{"properties": {"fontSize": literal(10)}}],
}


def cards(prefix, measures, y=86):
    gap, width = 10, (PAGE_WIDTH - 40 - 3 * 10) // 4
    return [visual(f"{prefix}Card{i}", "card", 20 + i * (width + gap), y, width, 104, {"Values": [measure(m)]})
            for i, m in enumerate(measures)]


def pages():
    month = column("dim_date", "month")
    category = column("dim_category", "category")
    store = column("dim_store", "store_name")
    region = column("dim_store", "region")
    channel = column("dim_store", "channel")

    overview = [
        header("ovHeader", "Calyx Home & Garden · 2025 management report", "Are we on track, and where?"),
        slicer("ovRegion", 700, region, "Region"),
        slicer("ovChannel", 890, channel, "Channel"),
        slicer("ovCategory", 1080, category, "Category"),
        *cards("ov", ["Net Sales", "Net Sales YoY %", "Gross Margin %", "Gross Margin vs Budget"]),
        visual("ovTrend", "lineChart", 20, 200, 770, 250,
               {"Category": [month], "Y": [measure("Net Sales"), measure("Net Sales LY"), measure("Budget")]},
               title="Net sales by month: 2025, last year and budget",
               objects={"dataPoint": series_colours({"Net Sales": BLUE, "Net Sales LY": MUTED_GREY, "Budget": ORANGE})}),
        visual("ovCategories", "clusteredBarChart", 800, 200, 460, 250,
               {"Category": [category], "Y": [measure("Net Sales YoY %")]},
               title="Growth vs last year by category", sort=(measure("Net Sales YoY %"), "Descending")),
        visual("ovStores", "tableEx", 20, 460, 1240, 250,
               {"Values": [store, measure("Net Sales"), measure("Net Sales YoY %"), measure("Net Sales vs Budget %"),
                           measure("Gross Margin %"), measure("Gross Margin vs Budget")]},
               title="Stores", sort=(measure("Net Sales vs Budget %"), "Ascending"), objects=TABLE_STYLE),
    ]
    margin = [
        header("mgHeader", "Margin & promotions", "What is eating the margin?"),
        slicer("mgRegion", 890, region, "Region"),
        slicer("mgChannel", 1080, channel, "Channel"),
        *cards("mg", ["Discount Rate", "Gross Margin %", "Gross Margin % Change (pts)", "Units YoY %"]),
        visual("mgTrend", "lineChart", 20, 200, 770, 250,
               {"Category": [month], "Y": [measure("Discount Rate"), measure("Gross Margin %")]},
               title="Discount rate and gross margin % by month",
               objects={"dataPoint": series_colours({"Discount Rate": ORANGE, "Gross Margin %": BLUE})}),
        visual("mgCategories", "clusteredBarChart", 800, 200, 460, 250,
               {"Category": [category], "Y": [measure("Gross Margin % Change (pts)")]},
               title="Gross margin % change vs last year (pts)",
               sort=(measure("Gross Margin % Change (pts)"), "Ascending")),
        visual("mgTable", "tableEx", 20, 460, 1240, 250,
               {"Values": [category, measure("Net Sales YoY %"), measure("Units YoY %"), measure("Discount Rate"),
                           measure("Gross Margin %"), measure("Gross Margin % LY"), measure("Return Rate")]},
               title="Categories: volume, price and margin", objects=TABLE_STYLE),
    ]
    stores = [
        header("stHeader", "Stores vs budget", "Which sites need attention?"),
        slicer("stRegion", 890, region, "Region"),
        slicer("stStore", 1080, store, "Store"),
        *cards("st", ["Net Sales", "Budget", "Net Sales vs Budget %", "Return Rate"]),
        visual("stVariance", "clusteredBarChart", 20, 200, 620, 510,
               {"Category": [store], "Y": [measure("Net Sales vs Budget %")]},
               title="Net sales vs budget by store", sort=(measure("Net Sales vs Budget %"), "Ascending")),
        visual("stTrend", "lineChart", 650, 200, 610, 250,
               {"Category": [month], "Y": [measure("Net Sales"), measure("Budget")]},
               title="Net sales vs budget by month",
               objects={"dataPoint": series_colours({"Net Sales": BLUE, "Budget": ORANGE})}),
        visual("stTable", "tableEx", 650, 460, 610, 250,
               {"Values": [store, measure("Net Sales"), measure("Budget"), measure("Net Sales vs Budget"),
                           measure("Return Rate")]},
               title="Store detail", sort=(measure("Net Sales vs Budget"), "Ascending"), objects=TABLE_STYLE),
    ]
    return [("Overview", "overview", overview),
            ("Margin & promotions", "margin", margin),
            ("Stores vs budget", "stores", stores)]


def year_filter() -> dict:
    """Report-level filter: the dashboard reports on 2025 (last year comes from the measures)."""
    return {"filters": [{
        "name": "yearFilter",
        "field": column("dim_date", "year"),
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "d", "Entity": "dim_date", "Type": 0}],
            "Where": [{"Condition": {"In": {
                "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": "year"}}],
                "Values": [[{"Literal": {"Value": "2025L"}}]],
            }}}],
        },
        "howCreated": "User",
    }]}


THEME = {
    "name": "Calyx",
    "dataColors": ["#2A78D6", "#898781", "#EB6834", "#1BAF7A", "#EDA100", "#E87BA4", "#4A3AA7", "#E34948"],
    "background": "#FFFFFF",
    "foreground": "#0B0B0B",
    "tableAccent": "#2A78D6",
    "good": "#0CA30C",
    "neutral": "#FAB219",
    "bad": "#D03B3B",
}


def write_report():
    definition = REPORT_DIR / "definition"
    definition.mkdir(parents=True, exist_ok=True)
    write_json(REPORT_DIR / "definition.pbir", {
        "$schema": SCHEMAS["pbir"], "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}},
    })
    write_json(definition / "version.json", {"$schema": SCHEMAS["version"], "version": "2.0.0"})
    write_json(REPORT_DIR / "StaticResources" / "RegisteredResources" / "CalyxTheme.json", THEME, schema=False)
    write_json(definition / "report.json", {
        "$schema": SCHEMAS["report"],
        "themeCollection": {"customTheme": {
            "name": "CalyxTheme.json",
            "reportVersionAtImport": {"visual": "2.2.0", "report": "3.0.0", "page": "2.0.0"},
            "type": "RegisteredResources",
        }},
        "filterConfig": year_filter(),
        "resourcePackages": [{
            "name": "RegisteredResources", "type": "RegisteredResources",
            "items": [{"name": "CalyxTheme.json", "path": "CalyxTheme.json", "type": "CustomTheme"}],
        }],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True},
    })
    page_list = pages()
    write_json(definition / "pages" / "pages.json", {
        "$schema": SCHEMAS["pages"],
        "pageOrder": [page_id for _, page_id, _ in page_list],
        "activePageName": page_list[0][1],
    })
    for display_name, page_id, visuals in page_list:
        page_dir = definition / "pages" / page_id
        write_json(page_dir / "page.json", {
            "$schema": SCHEMAS["page"], "name": page_id, "displayName": display_name,
            "displayOption": "FitToPage", "height": PAGE_HEIGHT, "width": PAGE_WIDTH,
        })
        for index, container in enumerate(visuals):
            container["position"]["z"] = index
            container["position"]["tabOrder"] = index
            write_json(page_dir / "visuals" / container["name"] / "visual.json", container)
    write_json(PBIP_DIR / f"{NAME}.pbip", {
        "$schema": SCHEMAS["pbip"], "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })
    write_text(PBIP_DIR / ".gitignore", "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")


# --- Files and validation -----------------------------------------------------------

WRITTEN_JSON = []


def write_json(path: Path, payload: dict, schema: bool = True):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    if schema:
        WRITTEN_JSON.append(path)


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def validate():
    """Check every report file against the schema named in its $schema property."""
    import urllib.request

    from jsonschema import Draft7Validator
    from referencing import Registry, Resource

    cache = {}

    def retrieve(uri: str):
        if uri not in cache:
            url = uri.replace("https://developer.microsoft.com/json-schemas/",
                              "https://raw.githubusercontent.com/microsoft/json-schemas/main/")
            with urllib.request.urlopen(url) as response:
                cache[uri] = Resource.from_contents(json.loads(response.read().decode("utf-8-sig")))
        return cache[uri]

    registry = Registry(retrieve=retrieve)
    problems = 0
    for path in WRITTEN_JSON:
        document = json.loads(path.read_text(encoding="utf-8"))
        schema = retrieve(document["$schema"]).contents
        validator = Draft7Validator(schema, registry=registry)
        for error in validator.iter_errors(document):
            problems += 1
            print(f"  {path.relative_to(PBIP_DIR)}: {error.json_path}: {error.message[:160]}")
    return problems


def main():
    if PBIP_DIR.exists():
        cache = MODEL_DIR / ".pbi"
        keep = None
        if cache.exists():  # keep Power BI Desktop's local data cache between rebuilds
            keep = PROJECT_DIR / ".pbi_cache_tmp"
            shutil.copytree(cache, keep, dirs_exist_ok=True)
        shutil.rmtree(PBIP_DIR)
        if keep:
            shutil.copytree(keep, cache, dirs_exist_ok=True)
            shutil.rmtree(keep)
    write_model()
    write_report()
    visuals = sum(len(v) for _, _, v in pages())
    print(f"PBIP written to {PBIP_DIR.relative_to(PROJECT_DIR)}: {len(TABLES)} tables, "
          f"{len(MEASURES)} measures, {len(RELATIONSHIPS)} relationships, 3 pages, {visuals} visuals")
    if "--no-validate" not in sys.argv:
        problems = validate()
        print(f"Schema validation: {len(WRITTEN_JSON)} files, {problems} problem(s)")
        sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
