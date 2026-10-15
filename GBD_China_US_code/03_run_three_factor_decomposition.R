options(stringsAsFactors = FALSE, scipen = 999)

args <- commandArgs(trailingOnly = TRUE)
input_dir <- if (length(args) >= 1) args[[1]] else file.path(getwd(), "inputs")
output_dir <- if (length(args) >= 2) args[[2]] else file.path(getwd(), "outputs")
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

start_year <- 1990L
end_year <- 2023L
sex_keep <- "Both"
locations <- c("China", "United States of America")
age_levels <- c(
  "<5 years", "5-9 years", "10-14 years", "15-19 years",
  "20-24 years", "25-29 years", "30-34 years", "35-39 years",
  "40-44 years", "45-49 years", "50-54 years", "55-59 years",
  "60-64 years", "65-69 years", "70-74 years", "75-79 years",
  "80-84 years", "85-89 years", "90-94 years", "95+ years"
)
age_band_map <- c(
  "<5 years" = "<5",
  "5-9 years" = "5-19", "10-14 years" = "5-19", "15-19 years" = "5-19",
  "20-24 years" = "20-39", "25-29 years" = "20-39",
  "30-34 years" = "20-39", "35-39 years" = "20-39",
  "40-44 years" = "40-59", "45-49 years" = "40-59",
  "50-54 years" = "40-59", "55-59 years" = "40-59",
  "60-64 years" = "60-79", "65-69 years" = "60-79",
  "70-74 years" = "60-79", "75-79 years" = "60-79",
  "80-84 years" = "80+", "85-89 years" = "80+",
  "90-94 years" = "80+", "95+ years" = "80+"
)
age_band_levels <- c("<5", "5-19", "20-39", "40-59", "60-79", "80+")

input_files <- data.frame(
  location_name = rep(locations, each = 2),
  measure_short = rep(c("Prevalence", "DALYs"), times = 2),
  file_name = c("china pre.csv", "China DALY.csv", "US pre.csv", "US DALY.csv"),
  stringsAsFactors = FALSE
)

read_gbd <- function(path) {
  read.csv(path, check.names = FALSE, fileEncoding = "UTF-8-BOM")
}

population_path <- file.path(input_dir, "population.csv")
if (!file.exists(population_path)) stop("Missing population file: ", population_path)
pop_raw <- read_gbd(population_path)

required_cols_pop <- c("location_name", "sex_name", "age_name", "metric_name", "year", "val")
missing_cols_pop <- setdiff(required_cols_pop, names(pop_raw))
if (length(missing_cols_pop)) stop("Population file missing columns: ", paste(missing_cols_pop, collapse = ", "))

pop <- pop_raw[
  pop_raw$location_name %in% locations & pop_raw$sex_name == sex_keep &
    pop_raw$metric_name == "Number" & pop_raw$year %in% c(start_year, end_year),
  required_cols_pop
]

qa_rows <- list()
add_qa <- function(check_name, scope, observed, expected, passed, severity = "critical", note = "") {
  qa_rows[[length(qa_rows) + 1L]] <<- data.frame(
    check_name = check_name, scope = scope, observed = as.character(observed),
    expected = as.character(expected), passed = as.logical(passed),
    severity = severity, note = note, stringsAsFactors = FALSE
  )
}

for (loc in locations) {
  for (yr in c(start_year, end_year)) {
    p <- pop[pop$location_name == loc & pop$year == yr, ]
    age_specific <- p[p$age_name %in% age_levels, ]
    all_age <- p[p$age_name == "All ages", ]
    add_qa("population_age_count", paste(loc, yr), nrow(age_specific), length(age_levels), nrow(age_specific) == length(age_levels))
    add_qa("population_age_duplicates", paste(loc, yr), sum(duplicated(age_specific$age_name)), 0, !anyDuplicated(age_specific$age_name))
    missing_ages <- setdiff(age_levels, age_specific$age_name)
    add_qa("population_age_coverage", paste(loc, yr), paste(missing_ages, collapse = ";"), "none", length(missing_ages) == 0)
    if (nrow(all_age) == 1L) {
      diff <- sum(age_specific$val) - all_age$val
      tol <- max(1e-6, abs(all_age$val) * 1e-10)
      add_qa("population_all_age_reconciliation", paste(loc, yr), format(diff, digits = 16), 0, abs(diff) <= tol)
    } else {
      add_qa("population_all_age_reconciliation", paste(loc, yr), nrow(all_age), 1, FALSE, note = "All ages row missing or duplicated")
    }
  }
}

pop_age <- pop[pop$age_name %in% age_levels, c("location_name", "year", "age_name", "val")]
names(pop_age)[names(pop_age) == "val"] <- "population"

factor_labels <- c(
  aging = "Population aging",
  population = "Population growth",
  epidemiological = "Epidemiological change"
)

decompose_age <- function(pop1, pop2, r1, r2) {
  p1 <- sum(pop1)
  p2 <- sum(pop2)
  a1 <- pop1 / p1
  a2 <- pop2 / p2

  aging <- (a2*p1*r1 + a2*p2*r2)/3 + (a2*p1*r2 + a2*p2*r1)/6 -
    (a1*p1*r1 + a1*p2*r2)/3 - (a1*p1*r2 + a1*p2*r1)/6
  population <- (a1*p2*r1 + a2*p2*r2)/3 + (a1*p2*r2 + a2*p2*r1)/6 -
    (a1*p1*r1 + a2*p1*r2)/3 - (a1*p1*r2 + a2*p1*r1)/6
  epidemiological <- (a1*p1*r2 + a2*p2*r2)/3 + (a1*p2*r2 + a2*p1*r2)/6 -
    (a1*p1*r1 + a2*p2*r1)/3 - (a1*p2*r1 + a2*p1*r1)/6

  data.frame(
    age_name = age_levels,
    aging = aging,
    population = population,
    epidemiological = epidemiological,
    stringsAsFactors = FALSE
  )
}

main_results <- list()
long_results <- list()
age_results <- list()

for (fidx in seq_len(nrow(input_files))) {
  spec <- input_files[fidx, ]
  path <- file.path(input_dir, spec$file_name)
  if (!file.exists(path)) stop("Missing disease file: ", path)
  d <- read_gbd(path)
  required_cols <- c("location_name", "sex_name", "age_name", "cause_name", "metric_name", "year", "val")
  missing_cols <- setdiff(required_cols, names(d))
  if (length(missing_cols)) stop(spec$file_name, " missing columns: ", paste(missing_cols, collapse = ", "))

  d <- d[d$location_name == spec$location_name & d$sex_name == sex_keep & d$year %in% c(start_year, end_year), ]
  causes <- sort(unique(d$cause_name))
  add_qa("cause_count", paste(spec$location_name, spec$measure_short), length(causes), 20, length(causes) == 20)

  for (cause in causes) {
    rate <- d[d$cause_name == cause & d$metric_name == "Rate" & d$age_name %in% age_levels, c("year", "age_name", "val")]
    number_age <- d[d$cause_name == cause & d$metric_name == "Number" & d$age_name %in% age_levels, c("year", "age_name", "val")]
    number_all <- d[d$cause_name == cause & d$metric_name == "Number" & d$age_name == "All ages", c("year", "val")]

    key_scope <- paste(spec$location_name, spec$measure_short, cause, sep = " | ")
    add_qa("rate_row_count", key_scope, nrow(rate), 2 * length(age_levels), nrow(rate) == 2 * length(age_levels))
    add_qa("rate_key_duplicates", key_scope, sum(duplicated(rate[c("year", "age_name")])), 0, !anyDuplicated(rate[c("year", "age_name")]))
    add_qa("number_row_count", key_scope, nrow(number_age), 2 * length(age_levels), nrow(number_age) == 2 * length(age_levels))

    if (nrow(rate) != 2 * length(age_levels) || anyDuplicated(rate[c("year", "age_name")])) next

    p1df <- pop_age[pop_age$location_name == spec$location_name & pop_age$year == start_year, ]
    p2df <- pop_age[pop_age$location_name == spec$location_name & pop_age$year == end_year, ]
    r1df <- rate[rate$year == start_year, ]
    r2df <- rate[rate$year == end_year, ]
    p1 <- p1df$population[match(age_levels, p1df$age_name)]
    p2 <- p2df$population[match(age_levels, p2df$age_name)]
    r1 <- r1df$val[match(age_levels, r1df$age_name)] / 1e5
    r2 <- r2df$val[match(age_levels, r2df$age_name)] / 1e5

    complete <- all(is.finite(c(p1, p2, r1, r2)))
    add_qa("merge_coverage", key_scope, sum(is.finite(c(p1, p2, r1, r2))), 4 * length(age_levels), complete)
    if (!complete) next

    age_effects <- decompose_age(p1, p2, r1, r2)
    totals <- colSums(age_effects[c("aging", "population", "epidemiological")])
    baseline <- sum(p1 * r1)
    endpoint <- sum(p2 * r2)
    overall <- endpoint - baseline
    residual <- sum(totals) - overall
    tol <- max(1e-7, abs(overall) * 1e-10, abs(endpoint) * 1e-12)
    add_qa("decomposition_identity", key_scope, format(residual, digits = 16), 0, abs(residual) <= tol)

    all1 <- number_all$val[number_all$year == start_year]
    all2 <- number_all$val[number_all$year == end_year]
    rec1 <- if (length(all1) == 1L) baseline - all1 else NA_real_
    rec2 <- if (length(all2) == 1L) endpoint - all2 else NA_real_
    rec_tol1 <- if (length(all1) == 1L) max(0.5, abs(all1) * 5e-7) else NA_real_
    rec_tol2 <- if (length(all2) == 1L) max(0.5, abs(all2) * 5e-7) else NA_real_
    add_qa("burden_all_age_reconciliation_1990", key_scope, format(rec1, digits = 12), 0, is.finite(rec1) && abs(rec1) <= rec_tol1, severity = "high")
    add_qa("burden_all_age_reconciliation_2023", key_scope, format(rec2, digits = 12), 0, is.finite(rec2) && abs(rec2) <= rec_tol2, severity = "high")

    effects <- as.numeric(totals)
    names(effects) <- names(totals)
    dominant <- names(effects)[which.max(abs(effects))]
    sign_nonzero <- sign(effects[abs(effects) > tol])
    offsetting <- length(unique(sign_nonzero)) > 1L

    main_results[[length(main_results) + 1L]] <- data.frame(
      location_name = spec$location_name,
      measure = spec$measure_short,
      cause_name = cause,
      start_year = start_year,
      end_year = end_year,
      baseline = baseline,
      endpoint = endpoint,
      overall_change = overall,
      total_pct_change = if (baseline != 0) overall / baseline * 100 else NA_real_,
      aging_effect = effects[["aging"]],
      population_effect = effects[["population"]],
      epidemiological_effect = effects[["epidemiological"]],
      aging_baseline_pct = if (baseline != 0) effects[["aging"]] / baseline * 100 else NA_real_,
      population_baseline_pct = if (baseline != 0) effects[["population"]] / baseline * 100 else NA_real_,
      epidemiological_baseline_pct = if (baseline != 0) effects[["epidemiological"]] / baseline * 100 else NA_real_,
      aging_net_share_pct = if (abs(overall) > tol) effects[["aging"]] / overall * 100 else NA_real_,
      population_net_share_pct = if (abs(overall) > tol) effects[["population"]] / overall * 100 else NA_real_,
      epidemiological_net_share_pct = if (abs(overall) > tol) effects[["epidemiological"]] / overall * 100 else NA_real_,
      dominant_factor = factor_labels[[dominant]],
      offsetting_factors = offsetting,
      decomposition_residual = residual,
      stringsAsFactors = FALSE
    )

    for (factor_name in names(factor_labels)) {
      effect <- effects[[factor_name]]
      long_results[[length(long_results) + 1L]] <- data.frame(
        location_name = spec$location_name, measure = spec$measure_short,
        cause_name = cause, factor = factor_labels[[factor_name]],
        effect = effect,
        baseline_pct = if (baseline != 0) effect / baseline * 100 else NA_real_,
        net_change_share_pct = if (abs(overall) > tol) effect / overall * 100 else NA_real_,
        stringsAsFactors = FALSE
      )
    }

    age_effects$age_band <- unname(age_band_map[age_effects$age_name])
    for (band in age_band_levels) {
      idx <- age_effects$age_band == band
      for (factor_name in names(factor_labels)) {
        value <- sum(age_effects[[factor_name]][idx])
        total_factor <- effects[[factor_name]]
        age_results[[length(age_results) + 1L]] <- data.frame(
          location_name = spec$location_name, measure = spec$measure_short,
          cause_name = cause, age_band = band,
          factor = factor_labels[[factor_name]], contribution = value,
          factor_composition_pct = if (abs(total_factor) > tol) value / total_factor * 100 else NA_real_,
          overall_change_share_pct = if (abs(overall) > tol) value / overall * 100 else NA_real_,
          stringsAsFactors = FALSE
        )
      }
    }
  }
}

main <- do.call(rbind, main_results)
long <- do.call(rbind, long_results)
age_contrib <- do.call(rbind, age_results)
qa <- do.call(rbind, qa_rows)

age_sum <- aggregate(contribution ~ location_name + measure + cause_name + factor, age_contrib, sum)
names(age_sum)[names(age_sum) == "contribution"] <- "age_band_sum"
age_check <- merge(age_sum, long[c("location_name", "measure", "cause_name", "factor", "effect")],
                   by = c("location_name", "measure", "cause_name", "factor"), all.x = TRUE)
age_check$residual <- age_check$age_band_sum - age_check$effect
for (i in seq_len(nrow(age_check))) {
  tol <- max(1e-7, abs(age_check$effect[i]) * 1e-10)
  add_qa("age_band_identity",
         paste(age_check$location_name[i], age_check$measure[i], age_check$cause_name[i], age_check$factor[i], sep = " | "),
         format(age_check$residual[i], digits = 16), 0, abs(age_check$residual[i]) <= tol)
}
qa <- do.call(rbind, qa_rows)

if (any(!qa$passed & qa$severity == "critical")) {
  write.csv(qa, file.path(output_dir, "quality_checks.csv"), row.names = FALSE, fileEncoding = "UTF-8")
  stop("Critical quality checks failed. See quality_checks.csv")
}

main <- main[order(main$measure, main$location_name, -abs(main$overall_change)), ]
long <- long[order(long$measure, long$location_name, long$cause_name, long$factor), ]
age_contrib$age_band <- factor(age_contrib$age_band, levels = age_band_levels)
age_contrib <- age_contrib[order(age_contrib$measure, age_contrib$location_name, age_contrib$cause_name, age_contrib$factor, age_contrib$age_band), ]
age_contrib$age_band <- as.character(age_contrib$age_band)

write.csv(main, file.path(output_dir, "decomposition_main.csv"), row.names = FALSE, fileEncoding = "UTF-8")
write.csv(long, file.path(output_dir, "decomposition_factors_long.csv"), row.names = FALSE, fileEncoding = "UTF-8")
write.csv(age_contrib, file.path(output_dir, "decomposition_age_band_contributions.csv"), row.names = FALSE, fileEncoding = "UTF-8")
write.csv(qa, file.path(output_dir, "quality_checks.csv"), row.names = FALSE, fileEncoding = "UTF-8")

cat("Completed", nrow(main), "country-measure-cause decompositions\n")
cat("Quality checks:", sum(qa$passed), "passed;", sum(!qa$passed), "failed\n")
