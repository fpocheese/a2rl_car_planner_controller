# Reported aggregate results: provenance and use

## Status

`reported_aggregate_results.json` is the machine-readable source for the
comparison, ablation, headline, and seed-summary values printed in the
manuscript. The authors have confirmed that these are the true aggregate
results of the HIL campaigns described in the paper.

The file is not a substitute for the per-lap record. The underlying per-lap
files remain on the authors' remote experimental server, which is temporarily
inaccessible. No per-lap samples, seed values, scenario assignments, failure
labels, or timing distributions have been inferred or synthesized from the
reported aggregates.

## Reproducible checks available now

`verify_reported_aggregates.py` checks that:

1. every reported OSR agrees with its integer success count and 1,000-lap
   denominator;
2. the 947/1,000 headline result yields the reported two-sided 95% exact
   Clopper--Pearson interval;
3. the two-sided pooled two-proportion tests and separate Holm adjustments for
   the four baselines and four ablations satisfy the manuscript statement;
4. every numeric cell in the comparison and ablation LaTeX tables matches the
   JSON source.

The count-level tests remain descriptive because aggregates do not preserve
scenario or training-seed clustering. The five-policy value of 94.3% +/- 0.7%
is therefore retained as an author-confirmed summary, without reconstructing
the five underlying rates.

## Required archive completion

When access to the remote server is restored, the authors should deposit a
versioned archive containing per-lap identifiers, scenario family, initial
conditions, opponent policy and version, training seed, checkpoint identifier,
success/failure status, collision and track events, TTO, minimum gap, TTC,
planning-cycle feasibility counts, and timing/fallback records. The deposited
README should map those fields to the manuscript tables and record the script
revision and environment used to regenerate them.
