# Evaluation methodology

## Pipeline

1. **Select** an allowlisted `(task, candidate)` pair by ID (see `SECURITY.md`).
2. **Verify and load** the digest-pinned fixture.
3. **Run checks.** Each declared check in the task manifest runs in a fresh temp directory and
   records evidence. Every assertion has a stable ID such as `T2-S01:cross_tenant_status`, plus
   expected and actual values and an `ok` flag.
4. **Classify** each check:
   - `PASS`: every assertion held.
   - `FAIL`: the **candidate** violated an assertion. This includes the candidate raising, returning
     a malformed response or breaking its constructor contract.
   - `ERROR`: the **evaluator** could not establish behaviour. Examples are an oracle exception, an
     unverifiable store, a bounded join that timed out, no assertions recorded, or duplicate evidence IDs.
   - `MISSING`: a declared check produced no result.
5. **Score and gate** with the shared scorer (`RUBRIC.md`).
6. **Report** canonical JSON and Markdown from the same structure. Feedback is produced for each
   FAIL, ERROR or MISSING.

## Evidence kinds, kept separate

| Kind | Where it lives | What it can claim |
|---|---|---|
| Observed test evidence | `checks[].evidence` and `feedback[].observed_violation` | That the candidate behaved this way under these inputs |
| Suspected cause | `feedback[].suspected_cause` | A likely explanation, marked *not proven by the tests* |
| Source-inspection notes | `fixtures/*/DEFECTS.md` (fixture author) | Root cause with code locations. Never read by the evaluator |
| Calibration expectation | `calibration/expected-outcomes.json` | Which checks the seeded defects *should* fail. Compared after scoring and never used for scoring |
| Provenance | Report `candidate.provenance` and `review_source` | Fixtures are AI-assisted and pending owner review. Annotations are `synthetic_example` |

Evidence records sensitive **categories** and key names, never sensitive values. This means a report
cannot repeat a leak it detected.

## Calibration

`python -m code_eval_lab evaluate-suite` evaluates all nine registered candidates and compares
each result with the calibration expectations. The suite is **CALIBRATED** only when:

- every evaluation is COMPLETE;
- every reference passes;
- every seeded defect fails exactly its expected checks with the expected verdict.

A flawed candidate counts as "correctly handled" when it is detected, never when the harness merely
ran.

## Annotation agreement (demonstration)

`python -m code_eval_lab agreement` computes paired-label metrics over
`annotations/synthetic-agreement-example.json`:

- **Exact agreement** = matching labels divided by the number of paired items.
- **Unweighted Cohen's kappa** = (p_o − p_e) / (1 − p_e). Here p_e = Σ_c p_A(c) · p_B(c), using each
  reviewer's category marginals over the paired items.
- An item is **paired** only if both reviewers gave a non-null category. Null categories are
  reported as missing labels. Items labelled by one reviewer only are reported as unpaired.
  Duplicates, unknown categories or provenance, and out-of-band scores reject the whole set.
- **Undefined** values: zero paired items (both metrics), or p_e = 1 (kappa). These are reported as
  `null` with a reason, never as 0 or as perfect agreement.
- Arithmetic uses exact fractions (`fractions.Fraction`), and the output shows both the fraction
  and a 4-decimal value.

The bundled example has six hand-crafted items. Exact agreement is 2/3, expected agreement 1/3 and
kappa 1/2. **These labels are not from independent reviewers.** They only show that the computation
is right. Agreement is not accuracy, and six synthetic items cannot support any reliability claim.

## Limitations

- **Fixtures, not a benchmark.** Three tasks with three controlled fixtures each. There are no
  hidden tests, no real model outputs and no population claims.
- **Shared blind spots.** The reference and the checks were written together, so a misconception
  common to both would go unnoticed.
- **In-process execution.** This relies on owner review, not isolation.
- **Timing.** Wall time is deliberately excluded from canonical output. Nothing here is a
  performance, throughput or cost measurement.
