# 02 - Analyse housing prices in the Lille metropolitan area (DVF 2021-2025)
#
# 1. Raw trends: median price per m2 by year, flats vs houses.
# 2. Communes: where a square metre costs the most and the least (2024-2025).
# 3. A quality-adjusted (hedonic) price index: medians move when the MIX of homes sold changes;
#    a regression with commune, size and type controls isolates the pure price effect of each year.
# 4. A valuation model: estimate a home's price from its characteristics, measure the error on
#    sales the model has not seen, and flag sales far from the market price.
#
# Outputs: results/summary.json (for the web page), results/*.csv, images/*.png

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(tidyr)
  library(ggplot2)
  library(scales)
  library(broom)
  library(jsonlite)
})

project_dir <- getwd()
sales <- read_csv(file.path(project_dir, "data", "processed", "mel_sales.csv.gz"), show_col_types = FALSE)
dir.create(file.path(project_dir, "results"), showWarnings = FALSE)
dir.create(file.path(project_dir, "images"), showWarnings = FALSE)
set.seed(59)

blue <- "#2a78d6"; orange <- "#eb6834"; grey <- "#898781"
theme_portfolio <- theme_minimal(base_size = 11) +
  theme(panel.grid.minor = element_blank(), panel.grid.major = element_line(colour = "#e1e0d9", linewidth = 0.4),
        plot.title = element_text(face = "bold", size = 13), plot.title.position = "plot",
        legend.position = "top", legend.justification = "left", axis.title = element_text(colour = "#52514e"))

# --- 1. Raw trends ------------------------------------------------------------------------
yearly <- sales |>
  group_by(year, type) |>
  summarise(sales = n(), median_price_m2 = median(price_m2), median_price = median(price),
            median_surface = median(surface), .groups = "drop")
lille_yearly <- sales |>
  filter(commune == "Lille") |>
  group_by(year, type) |>
  summarise(sales = n(), median_price_m2 = median(price_m2), .groups = "drop")
write_csv(yearly, file.path(project_dir, "results", "yearly_medians.csv"))

p1 <- ggplot(yearly, aes(year, median_price_m2, colour = type)) +
  geom_line(linewidth = 1) + geom_point(size = 2.4, shape = 21, fill = "white", stroke = 1.4) +
  scale_colour_manual(values = c(Flat = blue, House = orange), name = NULL) +
  scale_y_continuous(labels = label_comma(suffix = " €"), limits = c(0, NA)) +
  labs(title = "Median price per m², Lille metropolitan area", x = NULL, y = NULL) +
  theme_portfolio
ggsave(file.path(project_dir, "images", "trend.png"), p1, width = 7, height = 4, dpi = 150, bg = "white")

# --- 2. Communes ----------------------------------------------------------------------------
recent <- filter(sales, year >= 2024)
communes <- recent |>
  group_by(commune) |>
  summarise(sales = n(), median_price_m2 = median(price_m2), flats_share = mean(type == "Flat"),
            .groups = "drop") |>
  filter(sales >= 150) |>
  arrange(desc(median_price_m2))
write_csv(communes, file.path(project_dir, "results", "communes_2024_2025.csv"))

top_communes <- communes |> slice_max(sales, n = 20)
p2 <- ggplot(top_communes, aes(median_price_m2, reorder(commune, median_price_m2))) +
  geom_col(fill = blue, width = 0.6) +
  geom_text(aes(label = comma(round(median_price_m2), suffix = " €")), hjust = -0.1, size = 3.2, colour = "#0b0b0b") +
  scale_x_continuous(labels = label_comma(suffix = " €"), expand = expansion(mult = c(0, 0.15))) +
  labs(title = "Median price per m² in the 20 busiest communes (2024-2025)", x = NULL, y = NULL) +
  theme_portfolio + theme(panel.grid.major.y = element_blank())
ggsave(file.path(project_dir, "images", "communes.png"), p2, width = 7, height = 5.2, dpi = 150, bg = "white")

p3 <- ggplot(filter(recent, !is.na(longitude)), aes(longitude, latitude, colour = pmin(price_m2, 6000))) +
  geom_point(size = 0.35, alpha = 0.7) +
  scale_colour_gradient(low = "#cde2fb", high = "#0d366b", labels = label_comma(suffix = " €"), name = "Price per m²") +
  coord_quickmap() +
  labs(title = "Every sale of 2024-2025, coloured by price per m²", x = NULL, y = NULL) +
  theme_portfolio + theme(axis.text = element_blank(), panel.grid.major = element_blank(),
                          legend.position = "right", legend.justification = "center")
ggsave(file.path(project_dir, "images", "map.png"), p3, width = 7, height = 6, dpi = 150, bg = "white")

# --- 3. Quality-adjusted price index --------------------------------------------------------
index_model <- lm(log(price_m2) ~ factor(year) + type + log(surface) + rooms + commune, data = sales)
year_effects <- tidy(index_model) |>
  filter(grepl("factor\\(year\\)", term)) |>
  transmute(year = as.integer(sub("factor\\(year\\)", "", term)), hedonic = exp(estimate) * 100)
index <- bind_rows(tibble(year = 2021L, hedonic = 100), year_effects) |> arrange(year)
raw_index <- sales |> group_by(year) |> summarise(median = median(price_m2), .groups = "drop") |>
  mutate(raw = median / first(median) * 100)
index <- left_join(index, select(raw_index, year, raw), by = "year")
write_csv(index, file.path(project_dir, "results", "price_index.csv"))

p4 <- index |>
  pivot_longer(c(hedonic, raw), names_to = "index", values_to = "value") |>
  mutate(index = recode(index, hedonic = "Quality-adjusted (regression)", raw = "Raw median")) |>
  ggplot(aes(year, value, colour = index)) +
  geom_hline(yintercept = 100, colour = "#c3c2b7") +
  geom_line(linewidth = 1) + geom_point(size = 2.4, shape = 21, fill = "white", stroke = 1.4) +
  scale_colour_manual(values = c("Quality-adjusted (regression)" = blue, "Raw median" = grey), name = NULL) +
  labs(title = "Price index, 2021 = 100", x = NULL, y = NULL) +
  theme_portfolio
ggsave(file.path(project_dir, "images", "index.png"), p4, width = 7, height = 4, dpi = 150, bg = "white")

# --- 4. Valuation model ---------------------------------------------------------------------
sales <- sales |> mutate(quarter = paste0(year, "-Q", (as.integer(format(date, "%m")) - 1) %/% 3 + 1))
in_test <- sample(c(TRUE, FALSE), nrow(sales), replace = TRUE, prob = c(0.2, 0.8))
train <- sales[!in_test, ]
test <- sales[in_test, ]
valuation <- lm(log(price) ~ log(surface) * type + rooms + commune + quarter, data = train)
test <- test |>
  filter(commune %in% train$commune, quarter %in% train$quarter) |>
  mutate(estimate = exp(predict(valuation, newdata = pick(everything()))),
         gap = price / estimate - 1)
model_quality <- list(
  r_squared = round(glance(valuation)$r.squared, 3),
  test_sales = nrow(test),
  median_abs_error_pct = round(median(abs(test$gap)) * 100, 1),
  within_20_pct = round(mean(abs(test$gap) <= 0.20) * 100, 1),
  above_30_pct = round(mean(test$gap > 0.30) * 100, 1),
  below_30_pct = round(mean(test$gap < -0.30) * 100, 1),
  above_50_pct = round(mean(test$gap > 0.50) * 100, 1),
  below_50_pct = round(mean(test$gap < -0.50) * 100, 1)
)
coefficients <- tidy(valuation) |> filter(term %in% c("log(surface)", "typeHouse", "rooms", "log(surface):typeHouse"))

p5 <- ggplot(test, aes(estimate, price)) +
  geom_point(alpha = 0.15, size = 0.6, colour = blue) +
  geom_abline(slope = 1, intercept = 0, colour = orange, linewidth = 0.8) +
  scale_x_log10(labels = label_comma(suffix = " €")) + scale_y_log10(labels = label_comma(suffix = " €")) +
  labs(title = "Sale price against the model's estimate (sales not used for training)",
       x = "Estimated price", y = "Actual price") +
  theme_portfolio
ggsave(file.path(project_dir, "images", "valuation.png"), p5, width = 7, height = 4.6, dpi = 150, bg = "white")

# Example: what is a 60 m2, 3-room flat worth in Lille, Roubaix and Marcq-en-Baroeul in late 2025?
example <- expand_grid(commune = c("Lille", "Roubaix", "Marcq-en-Barœul", "Villeneuve-d'Ascq"),
                       type = "Flat", surface = 60, rooms = 3, quarter = "2025-Q4") |>
  filter(commune %in% train$commune)
example$estimate <- round(exp(predict(valuation, newdata = example)), -3)

# --- Summary for the web page ----------------------------------------------------------------
latest <- yearly |> filter(year == max(year))
peak <- yearly |> group_by(type) |> slice_max(median_price_m2, n = 1, with_ties = FALSE) |> ungroup()
steps <- fromJSON(file.path(project_dir, "data", "processed", "preparation_steps.json"))
summary <- list(
  source = "DVF geolocalised, Etalab / DGFiP, 2021-2025",
  preparation = steps,
  sales = nrow(sales),
  communes_in_data = n_distinct(sales$commune),
  yearly = yearly,
  lille_yearly = lille_yearly,
  peak = peak,
  latest = latest,
  index = index,
  communes = communes,
  model = model_quality,
  coefficients = coefficients |> mutate(across(where(is.numeric), \(x) round(x, 4))),
  example = example
)
write_json(summary, file.path(project_dir, "results", "summary.json"), auto_unbox = TRUE, pretty = TRUE, digits = NA)
writeLines(c("// Generated by R/02_analysis.R - do not edit by hand.",
             paste0("window.HOUSING_SUMMARY = ", toJSON(summary, auto_unbox = TRUE, digits = NA), ";")),
           file.path(project_dir, "results", "summary.js"), useBytes = TRUE)

cat("Yearly medians (EUR per m2):\n"); print(yearly |> select(year, type, sales, median_price_m2) |> pivot_wider(names_from = type, values_from = c(sales, median_price_m2)))
cat("\nIndex (2021 = 100):\n"); print(index)
cat("\nMost / least expensive communes 2024-2025:\n"); print(head(communes, 5)); print(tail(communes, 5))
cat("\nValuation model:\n"); print(unlist(model_quality)); print(coefficients)
cat("\nExample 60 m2 flat:\n"); print(example)
