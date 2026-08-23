# Data and code repository plan

This author-facing plan implements the manuscript's Data Availability and Code
Availability commitments without inventing a repository or identifier. A
persistent DOI or accession must replace every bracketed field before
submission.

## Record A: representative HIL evidence

Recommended contents:

- `Eav24_default.json` and a README describing the plant configuration version;
- `case_02.json` and `case_05.json`, with `case_04_trimmed.json` retained in a
  clearly identified legacy subdirectory;
- `verify_representative_cases.py` and its expected output;
- checkpoint name and SHA-256 from `IMPLEMENTATION_EVIDENCE_AUDIT.md`;
- source checksums and the software environment;
- the two case-study source-figure sets, plotting environments, exact display
  transformations, and a panel-to-file map.

The repository landing page should identify this as source data for the two
representative engagements, not as the source of the 1000-lap aggregate tables.

## Record B0: aggregate results available in the submission package

The current package already contains:

- `reported_aggregate_results.json`, the author-confirmed headline,
  comparison, ablation, and five-policy summary values;
- `verify_reported_aggregates.py`, which recomputes the exact binomial interval,
  count-level tests and Holm adjustments and checks the LaTeX tables;
- `REPORTED_RESULTS_PROVENANCE.md`, which records that no per-lap values were
  reconstructed from the aggregates.

This record supports internal numeric verification and table regeneration. It
does not replace the lap-level campaign archive below.

## Record B: aggregate campaign and ablations

This record is required to support the headline result and Tables 5 and 6. It
should contain, for every method and ablation:

- one row per evaluation lap, including method, scenario family, scenario
  parameters, training seed, evaluation seed, checkpoint SHA-256, and source
  revision;
- pass, collision, off-track, minimum-gap, TTC, path-feasibility, termination,
  and deadline-miss fields with units and event definitions;
- the deterministic matched scenario schedule and checkpoint-selection rule;
- raw module and end-to-end timing samples;
- the versioned scripts that regenerate every table, confidence interval,
  adjusted test, and aggregate figure;
- a machine-readable manifest with file sizes and SHA-256 checksums.

## Repository metadata

Use a repository that issues a DOI or another persistent identifier, such as a
suitable institutional archive, Zenodo, Figshare, OSF, or another repository
approved by the authors' institution. The record needs a descriptive title,
authors, affiliations, abstract, version, file manifest, licence, keywords,
funding metadata, and a relation to the submitted article. The authors must
select the repository and licence.

## Ready-to-adapt statement after deposit

> The EAV24 plant configuration, representative HIL logs, case-study source
> data, checkpoint metadata, and verification script are available in
> [REPOSITORY] at [DOI]. The author-confirmed aggregate comparison and ablation
> values and their statistical verification script are available in
> [REPOSITORY] at [DOI]. The per-lap records, matched scenario schedule, timing
> samples, exact historical code archive, and analysis code underlying those
> results are available in [REPOSITORY] at [DOI].

## Author inputs still required

- repository name and persistent identifier for each record;
- authors/creators and final dataset title;
- licence and version;
- complete per-lap aggregate campaign archive;
- exact source revision and environment used for that campaign;
- confirmation that simulator/vendor files may be redistributed.
