
# Research Project Instructions

You are assisting with a quantitative finance research project targeting a high-quality IEEE Transactions journal.

## Project
NIFTY 50 Options Mispricing Detection Engine.

## Primary Rules

1. Treat the existing source code, datasets and reproducible outputs as the ground truth.
2. Never invent experimental results, metrics, equations, references or implementation details.
3. Distinguish IMPLEMENTED, PARTIALLY IMPLEMENTED, PLANNED and UNVERIFIED features.
4. Never claim a feature works merely because its documentation describes it.
5. Identify contradictions between source code, documentation, validation outputs and the LaTeX manuscript.
6. Trace every reported metric to its generating script, dataset and calculation.
7. Preserve original project files unless explicitly asked to modify them.
8. Never modify latexcode.tex during research or audit phases.
9. Do not generate synthetic data to strengthen empirical results.
10. Clearly identify data leakage, look-ahead bias, survivorship bias and statistical weaknesses.

## Research Standards

- Use rigorous mathematical reasoning.
- Evaluate models against established financial baselines.
- Separate forecasting accuracy, pricing accuracy, mispricing detection and trading profitability.
- Consider transaction costs, liquidity and market microstructure.
- Require out-of-sample validation.
- Report limitations honestly.
- Verify references before including them in the paper.
- Do not confuse statistical pricing deviations with proven economic mispricing.

## Token Efficiency

- Inspect only relevant files for each task.
- Avoid repeatedly reading the entire repository.
- Prefer targeted searches over dumping complete files.
- Save detailed findings in Markdown reports.
- Return concise summaries with file paths and line references.
- Do not repeat information already established in previous reports.

## Execution Safety

- Start with read-only inspection.
- Never overwrite datasets or existing validation outputs.
- Do not execute destructive commands.
- Do not modify source code without explicit approval.
- Before running expensive experiments, explain the required command and expected outputs.
- Keep all research findings traceable to actual project evidence.
