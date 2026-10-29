options(stringsAsFactors = FALSE, scipen = 999)

args <- commandArgs(trailingOnly = TRUE)
input_dir <- if (length(args) >= 1) args[[1]] else "inputs"
output_dir <- if (length(args) >= 2) args[[2]] else "outputs/decomposition"
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

years <- c(1990L, 2023L)
ages <- c(
  "<5 years", "5-9 years", "10-14 years", "15-19 years",
  "20-24 years", "25-29 years", "30-34 years", "35-39 years",
  "40-44 years", "45-49 years", "50-54 years", "55-59 years",
  "60-64 years", "65-69 years", "70-74 years", "75-79 years",
  "80-84 years", "85-89 years", "90-94 years", "95+ years"
)
age_bands <- c(
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

specs <- data.frame(
  location_name = rep(c("China", "United States of America"), each = 2),
  measure = rep(c("Prevalence", "DALYs"), 2),
  file_name = c("china pre.csv", "China DALY.csv", "US pre.csv", "US DALY.csv")
)

read_gbd <- function(path) read.csv(path, check.names = FALSE, fileEncoding = "UTF-8-BOM")

population <- read_gbd(file.path(input_dir, "population.csv"))
population <- population[
  population$sex_name == "Both" & population$metric_name == "Number" &
    population$year %in% years & population$age_name %in% ages,
  c("location_name", "year", "age_name", "val")
]

ordered_values <- function(data, year, value = "val") {
  part <- data[data$year == year, c("age_name", value)]
  if (nrow(part) != length(ages) || anyDuplicated(part$age_name)) {
    stop("Each year must contain one row for every age group")
  }
  part[[value]][match(ages, part$age_name)]
}

permutations <- rbind(
  c("aging", "population", "epidemiological"),
  c("aging", "epidemiological", "population"),
  c("population", "aging", "epidemiological"),
  c("population", "epidemiological", "aging"),
  c("epidemiological", "aging", "population"),
  c("epidemiological", "population", "aging")
)

decompose <- function(n1, n2, r1, r2) {
  components <- matrix(0, nrow = length(ages), ncol = 3,
                       dimnames = list(ages, c("aging", "population", "epidemiological")))
  shares <- list(aging = n1 / sum(n1), population = sum(n1), epidemiological = r1)
  target <- list(aging = n2 / sum(n2), population = sum(n2), epidemiological = r2)

  burden <- function(state) state$aging * state$population * state$epidemiological
  for (i in seq_len(nrow(permutations))) {
    state <- shares
    for (factor in permutations[i, ]) {
      before <- burden(state)
      state[[factor]] <- target[[factor]]
      components[, factor] <- components[, factor] + burden(state) - before
    }
  }
  components / nrow(permutations)
}

main_rows <- list()
long_rows <- list()
age_rows <- list()

for (i in seq_len(nrow(specs))) {
  spec <- specs[i, ]
  disease <- read_gbd(file.path(input_dir, spec$file_name))
  disease <- disease[
    disease$location_name == spec$location_name & disease$sex_name == "Both" &
      disease$metric_name == "Rate" & disease$year %in% years & disease$age_name %in% ages,
  ]
  pop <- population[population$location_name == spec$location_name, ]
  n1 <- ordered_values(pop, years[1])
  n2 <- ordered_values(pop, years[2])

  for (cause in sort(unique(disease$cause_name))) {
    rates <- disease[disease$cause_name == cause, ]
    r1 <- ordered_values(rates, years[1]) / 1e5
    r2 <- ordered_values(rates, years[2]) / 1e5
    parts <- decompose(n1, n2, r1, r2)
    effects <- colSums(parts)
    burden_1990 <- sum(n1 * r1)
    burden_2023 <- sum(n2 * r2)

    main_rows[[length(main_rows) + 1]] <- data.frame(
      location_name = spec$location_name, measure = spec$measure, cause_name = cause,
      burden_1990 = burden_1990, burden_2023 = burden_2023,
      total_change = burden_2023 - burden_1990,
      aging_effect = effects["aging"], population_effect = effects["population"],
      epidemiological_effect = effects["epidemiological"]
    )

    long_rows[[length(long_rows) + 1]] <- data.frame(
      location_name = spec$location_name, measure = spec$measure, cause_name = cause,
      factor = names(effects), contribution = as.numeric(effects)
    )

    detail <- data.frame(age_name = ages, parts, check.names = FALSE)
    detail$age_band <- unname(age_bands[detail$age_name])
    detail <- aggregate(cbind(aging, population, epidemiological) ~ age_band, detail, sum)
    detail$location_name <- spec$location_name
    detail$measure <- spec$measure
    detail$cause_name <- cause
    age_rows[[length(age_rows) + 1]] <- detail
  }
}

main <- do.call(rbind, main_rows)
if (any(abs(main$total_change - main$aging_effect - main$population_effect -
            main$epidemiological_effect) > pmax(1e-6, abs(main$total_change) * 1e-10))) {
  stop("Decomposition does not reconcile with the observed change")
}

write.csv(main, file.path(output_dir, "decomposition_main.csv"), row.names = FALSE)
write.csv(do.call(rbind, long_rows), file.path(output_dir, "decomposition_factors_long.csv"), row.names = FALSE)
write.csv(do.call(rbind, age_rows), file.path(output_dir, "decomposition_age_band_contributions.csv"), row.names = FALSE)
