# AI Logic Hardness

**AI Logic Hardness** is a private research and engineering project focused on improving the logical reasoning, planning, and reliability of AI systems.

The project explores how to make AI reasoning more robust against difficult problems, misleading assumptions, incomplete information, and multi-step errors. It emphasizes measurable improvements through carefully designed benchmarks, evaluation methods, and reasoning strategies rather than relying on unverified claims of better performance.

## Project goals

The initial goals are to develop a practical framework for:

| Area | Focus |
|---|---|
| **Problem hardness** | Classify tasks by logical depth, ambiguity, compositionality, adversarial pressure, and required consistency. |
| **Reasoning quality** | Evaluate whether an answer is correct, well-supported, internally consistent, and robust under small changes to the prompt. |
| **Reasoning strategies** | Test decomposition, self-verification, tool use, alternative-solution comparison, and structured planning. |
| **Error analysis** | Identify recurring failure modes such as hidden assumptions, invalid inference, arithmetic mistakes, and premature conclusions. |
| **Reliability** | Measure calibration, reproducibility, resistance to prompt variations, and performance on unfamiliar tasks. |

## Guiding principle

> Improve AI thinking by improving the quality of the problem-solving process that can be measured, tested, and verified.

The project should prioritize **observable evidence**—such as final answers, intermediate checkpoints, structured justifications, verification results, and test outcomes—over treating hidden model reasoning as automatically trustworthy. Sensitive or private internal reasoning should not be required for evaluation.

## Potential research directions

1. Build a taxonomy of logic-hard tasks across deduction, induction, abduction, planning, constraint satisfaction, causal reasoning, and quantitative problem solving.
2. Create benchmark items with controlled difficulty levels and adversarial variants.
3. Compare single-pass answers with structured approaches such as decomposition, independent solution generation, verification, and contradiction checking.
4. Develop metrics for correctness, consistency, completeness, efficiency, and resistance to perturbation.
5. Study when additional reasoning steps improve results and when they instead amplify an initial mistake.
6. Design reproducible experiments that record prompts, model settings, tool calls, outputs, judgments, and evaluation results.

## Suggested repository structure

```text
.
├── benchmarks/       # Logic-hard task sets and prompt variants
├── evaluations/      # Scoring rubrics and evaluation scripts
├── experiments/      # Reproducible experiment configurations
├── methods/          # Reasoning and verification strategies
├── analyses/         # Error analysis and research notes
├── data/             # Local or generated datasets; avoid committing secrets
└── README.md
```

## Working standards

Experiments should state their hypothesis, task distribution, model configuration, evaluation criteria, and known limitations. Results should be reproducible where possible, and benchmark contamination, evaluator bias, and prompt sensitivity should be considered explicitly.

Do not commit API keys, private user data, confidential prompts, or restricted datasets. When sharing results outside this private repository, remove sensitive information and distinguish clearly between measured findings, hypotheses, and speculation.

## Status

This repository is at the initial setup stage. The next step is to define the first benchmark specification and a baseline evaluation pipeline.

## License

No license has been selected yet because this repository is private. Add a license before publishing or distributing the project.

## Verifier-centered coding gates

The repository now includes a dependency-free gate runner in `gates/verify.py`. It turns the verifier-centered architecture into an executable approval check. The runner validates that requirements and invariants are present, limits the size of a change, executes tests, runs independent checks, scans the diff for common secret patterns, enforces dependency policy, audits the diff, and writes a machine-readable report.

Copy `examples/gates.config.json` into the repository root as `gates.config.json`, customize the requirements, invariants, commands, limits, and allowed paths, then run:

```bash
python3 -m gates.verify --config gates.config.json --root . --report gate-report.json
```

The runner exits with code `0` only when every gate passes. It exits with code `2` when it must **abstain** because a gate failed or evidence is missing, and code `3` for a configuration or execution error. Abstention is intentional: the system must not approve a change merely because it is plausible.

The report records the decision, failed gates, missing-evidence gates, command outputs, changed files, and other evidence needed for human review. The implementation is a safety-oriented baseline, not a formal proof of software correctness; gate configuration and coverage must be improved for each project.
