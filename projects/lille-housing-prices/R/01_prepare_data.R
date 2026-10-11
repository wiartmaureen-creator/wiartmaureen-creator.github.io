# 01 - Prepare the DVF sales of the Lille metropolitan area (MEL), 2021-2025
#
# Source: "Demandes de valeurs foncieres geolocalisees" (DVF), Etalab / DGFiP, open licence.
# https://files.data.gouv.fr/geo-dvf/latest/csv/ - one file per year for the Nord department (59).
#
# DVF has one row per property item of a sale: a single sale can contain a flat, a cellar and a
# parking space, all sharing the same total price. To compute a reliable price per square metre,
# we keep sales of exactly ONE dwelling (flat or house), with or without outbuildings.
#
# Output: data/processed/mel_sales.csv.gz (one row per sale)

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(jsonlite)
})

project_dir <- normalizePath(file.path(dirname(sys.frame(1)$ofile %||% "R/01_prepare_data.R"), ".."), mustWork = FALSE)
if (!dir.exists(file.path(project_dir, "data"))) project_dir <- getwd()
raw_dir <- file.path(project_dir, "data", "raw")
years <- 2021:2025

# Download the yearly files if they are missing (about 3 MB each).
dir.create(raw_dir, recursive = TRUE, showWarnings = FALSE)
for (year in years) {
  target <- file.path(raw_dir, sprintf("dvf_59_%d.csv.gz", year))
  if (!file.exists(target)) {
    url <- sprintf("https://files.data.gouv.fr/geo-dvf/latest/csv/%d/departements/59.csv.gz", year)
    download.file(url, target, mode = "wb", quiet = TRUE)
  }
}

# Communes of the Metropole Europeenne de Lille (geo.api.gouv.fr, EPCI 200093201).
communes <- fromJSON(file.path(project_dir, "data", "reference", "mel_communes.json")) |>
  transmute(code_commune = code, commune = nom, population)

raw <- bind_rows(lapply(years, function(year) {
  read_csv(file.path(raw_dir, sprintf("dvf_59_%d.csv.gz", year)), show_col_types = FALSE,
           col_types = cols(.default = col_character()))
}))

steps <- list(all_rows = nrow(raw))

sales <- raw |>
  filter(nature_mutation == "Vente", code_commune %in% communes$code_commune) |>
  mutate(valeur_fonciere = as.numeric(valeur_fonciere),
         surface_reelle_bati = as.numeric(surface_reelle_bati),
         nombre_pieces_principales = as.numeric(nombre_pieces_principales),
         longitude = as.numeric(longitude), latitude = as.numeric(latitude))
steps$mel_sale_rows <- nrow(sales)

one_dwelling <- sales |>
  group_by(id_mutation) |>
  filter(sum(type_local %in% c("Appartement", "Maison")) == 1,       # exactly one dwelling
         !any(type_local %in% "Local industriel. commercial ou assimilé")) |>  # no shop in the deal
  ungroup() |>
  filter(type_local %in% c("Appartement", "Maison"))
steps$single_dwelling_sales <- nrow(one_dwelling)

clean <- one_dwelling |>
  transmute(
    id_mutation,
    date = as.Date(date_mutation),
    year = as.integer(format(date, "%Y")),
    code_commune,
    type = if_else(type_local == "Appartement", "Flat", "House"),
    price = valeur_fonciere,
    surface = surface_reelle_bati,
    rooms = nombre_pieces_principales,
    price_m2 = price / surface,
    longitude, latitude
  ) |>
  left_join(communes, by = "code_commune") |>
  filter(!is.na(price), !is.na(surface), surface >= 10, surface <= 400,
         rooms >= 1, rooms <= 10, price >= 15000, price <= 3e6,
         price_m2 >= 500, price_m2 <= 12000)
steps$after_quality_filters <- nrow(clean)

out_dir <- file.path(project_dir, "data", "processed")
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
write_csv(clean, file.path(out_dir, "mel_sales.csv.gz"))
write_json(steps, file.path(out_dir, "preparation_steps.json"), auto_unbox = TRUE, pretty = TRUE)

cat(sprintf("Rows read: %s | MEL sale rows: %s | single-dwelling sales: %s | kept after quality filters: %s\n",
            format(steps$all_rows, big.mark = ","), format(steps$mel_sale_rows, big.mark = ","),
            format(steps$single_dwelling_sales, big.mark = ","), format(steps$after_quality_filters, big.mark = ",")))
print(clean |> count(year, type) |> tidyr::pivot_wider(names_from = type, values_from = n))
