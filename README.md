# ghost-data-audit

An evidence-first auditor that decides whether a person's personal data has **really** been deleted across many
systems, and, when it has not, produces the ordered plan to finish the job.

A deletion workflow can report "Complete" while data survives in replicas, logs, support attachments, exports, search
indexes, analytics rows, archives or backups, and while sync jobs or restores can recreate it. This tool treats workflow
statuses and activity results as **claims**, reconstructs the state of every related record at an audit cutoff from the
supplied evidence, applies a deletion policy, and returns `COMPLETE`, `INCOMPLETE` or `NOT_APPLICABLE` with ordered
findings, remediation and verification steps that cite their evidence.

It was built for the HackerRank Orchestrate "Ghost Data Still Exists" challenge. The challenge dataset is **not**
included in this repository.

## How it works

```
evidence files -> ingestion -> identity graph -> evidence index -> activity inference -> temporal state
                                                                              |
     output.csv <- strict validator <- remediation planner <- policy engine (deletion_rules.csv)
```

| Package | Role |
| --- | --- |
| `ghost_audit/ingestion/` | Parses JSON bundles and exports, SQLite snapshots (primary and replica tables), eight log dialects, handover text and PDF/PNG artifacts into observations: one statement about one resource at one time. |
| `ghost_audit/identity/` | Identity graph of users, current and historical emails, phones and hashes; edges keep source, validity and confidence; exact matches only. |
| `ghost_audit/investigation/` | Indexed evidence store, state classification (present/absent, exposed/clean, active/inactive), state at the audit cutoff, negative-evidence coverage, activity-based attribution of records that carry no identifier, per-case provenance. |
| `ghost_audit/policy/` | Rule engine driven by the rules CSV (delete, redact, anonymize, retain) and multilingual deletion-intent detection. |
| `ghost_audit/planning/` | Findings, remediation and verification in the mandated order, plus a dependency check that proves the order is safe. |
| `ghost_audit/output/` | Strict contract validator, `output.csv` writer, review queue and run manifest. |
| `ghost_audit/llm/` | Optional model stages (local Ollama or Anthropic): artifact text extraction and an intent second opinion, grounded, validated and token-accounted. |
| `ghost_audit/evaluation/` | Blind scoring, 22 hand-built cases, robustness suite, error taxonomy, structural comparator. |

Principles: evidence beats claims; time is a first-class dimension (nothing captured after the cutoff counts);
exact identifiers, never fuzzy merges; AI proposes, deterministic code validates.

## Usage

Requires Python 3.9 or newer; standard library only (tesseract is optional, for reading PNG artifacts).

```bash
# place the challenge data in ./dataset (deletion_requests.csv, user_identities.csv, evidence/, ...)
# or point to it:  export GHOST_DATASET_DIR=/path/to/dataset
python3 ghost_audit/main.py --no-llm        # deterministic run, writes output.csv
python3 ghost_audit/main.py                 # also uses a reachable local Ollama / ANTHROPIC_API_KEY
python3 ghost_audit/main.py --explain       # per-case provenance file
python3 ghost_audit/evaluation/main.py      # blind sample scoring + 22 evaluation cases
python3 ghost_audit/evaluation/robustness.py
```

Model options: `LLM_PROVIDER=ollama|anthropic|none`, `LLM_MODEL`, `OLLAMA_HOST`, `ANTHROPIC_API_KEY`.
Prompts mask emails, phones and hashes and treat request text as untrusted data.

## Results (challenge samples, scored blind)

| Metric | Result |
| --- | --- |
| Status accuracy | 32 / 32 |
| Step precision / recall / F1 | 1.000 / 0.984 / 0.992 |
| Exact step-list match | 29 / 32 |
| Recovery of attributed-by-activity records (blind probe) | 97 % |
| Output identical on Python 3.9, 3.10, 3.11, 3.12, 3.14 | yes |

On the challenge leaderboard the generated `output.csv` scored 28.5 / 30. Details and failure analysis are in
[`ghost_audit/evaluation/evaluation_report.md`](ghost_audit/evaluation/evaluation_report.md).

## Limitations

* Identifier-less records (a deleted account answers 404) are attributed from activity timing, which relies on
  properties of the synthetic challenge data; a real deployment needs foreign keys. Such cases are written to a review
  queue.
* Some identifiers appear in no evidence file and cannot be reported.
* Rule conditions in free text (shared ticket, exclusive attachment, partial legal hold) are assumed, not evaluated.
* No live-system queries and no verification that the requester owns the mailbox.
* `ghost_audit/media_facts.json` holds a human transcription of the challenge's screenshots and PDFs; unseen artifacts
  go through the text/OCR and model path.
