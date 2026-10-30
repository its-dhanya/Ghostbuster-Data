# Evaluation report

Command: `python3 ghost_audit/evaluation/main.py`. The 32 supplied sample cases are scored **blind**: the sample answers
are not used to infer anything for them (they are only used when producing the final `output.csv` to reserve the
resources they own). Metrics below are from that run.

## Sample results (32 cases, 111 gold steps)

| Metric | Result |
| --- | --- |
| Case-level `deletion_status` accuracy | 32 / 32 = 1.000 |
| Step precision / recall / F1 (operation + system + resource) | 1.000 / 0.984 / 0.992 |
| Sequence accuracy (exact `steps_json` equality) | 29 / 32 = 0.906 |
| Ordered-step similarity (LCS / gold steps) | 0.984 |
| Field accuracy on matched steps: phase, system_id, resource_id, operation, state, evidence_id | 1.000 each |
| Field accuracy on matched steps: step_no | 0.974 (only shifted by a missing step) |

Every sample case whose resource set is found is reproduced exactly, including step order, states and evidence IDs.

## Failures found and what was done

| Failure | Cause | Outcome |
| --- | --- | --- |
| `audit_record_6645`, `audit_record_5569` missing (cases 18, 20) | the ID occurs in no participant-visible file | not recoverable; 91 unlabeled cases have the same gap |
| `account_004` missing (case 4) | no activity, no evidence | not recoverable |
| `analytics_1895` / `analytics_4566` swapped (cases 25, 26) | two anonymized analytics rows, same day, no identifier | **fixed** by the per-case timing signature (below); earlier written off as an irreducible tie, which was wrong |
| Early version marked cases COMPLETE that were INCOMPLETE | pipe-delimited log dialect lost the `event` name | parser fixed; activity cross-check now finds no contradiction |
| Decoy account from months earlier attached to a case | same email appeared in an older cohort | 60-day look-back window on identifier links |
| Sample resources stolen by other cases | sample and unlabeled cases share activity windows | sample answers reserve their resources |
| French "suppression" and audit-style requests wrongly non-deletion | keyword list too narrow | default-to-deletion, explicit negation list, `CLASSIFY_REQUEST` cross-check |

## Unsupervised checks on the 518 unlabeled cases

* No contradiction between the predicted findings and the activity stream: every FAILED/PARTIAL/`CHECK_*` event on a linked resource appears as a finding, and every COMPLETE case has none.
* 60 findings concern records whose activity rows all say the action SUCCEEDED: the evidence shows them still present (claim versus state).
* All 1249 cited evidence IDs were captured at or before the case `audit_at`.
* The 10 `CLASSIFY_REQUEST` activity rows resolve exactly to the 10 non-deletion requests (cases 533-542).
* Only 10 of 539 account-deletion events remain unassigned.

## Robustness probe: activity-based inference and tie breaking

`python3 ghost_audit/evaluation/blind_account_test.py` hides the directly linked account of a random quarter of the hidden
cases (8 seeds, 472 trials) and asks the inference to recover it from activity alone.

| Version | Recovered |
| --- | --- |
| first version (wide time window, file overlap first) | 71 % |
| tight learned window + activity result matched to `reported_status` first | 85 % |
| + per-case timing signature and exact one-to-one assignment | **97.0 %** |

Why the last step works: all activity events of one case share a sub-minute jitter, `second(event) = base(case) +
constant(event kind)` (+-1 s). The constants are learned from identifier-linked cases (`Signature` in
`investigation/activity_inference.py`); a log-likelihood ratio then scores which unattributed deletion/anonymize/redact
event belongs to which case, and a maximum-weight one-to-one assignment (exact DP per connected component) picks the
pairing. Same-day cases that were pure coin flips are now separable. Other candidate signals were measured and are at
chance level (event offset in minutes vs. other events, vs. evidence observation times, vs. case/user/account number
order, vs. request-to-report span), so they are not used. Hedging (reporting both candidate accounts) was rejected: it
would tell an operator to delete another person's account. The residual 3 % are ties the signature cannot separate.

## Local-model experiment (Ollama, no key)

`LLM_PROVIDER=ollama python3 ghost_audit/main.py --use-llm` asked `llama3:latest` for a second opinion on the 398 distinct
request texts: 397 calls, 0 failed, 52,068 input + 7,979 output tokens (60,047 total, local so no cost). It disagreed
with the rules on exactly one text (a request to verify that a deletion happened, which the model read as non-deletion;
the rules were right and were kept). `output.csv` was byte-identical to the deterministic run, so the submitted
file and `usage_report.md` come from the deterministic run. The images and PDFs cannot be read by any installed local
model (none is a vision model), so that step stays on the human transcription.

## Uncertainty, side files and cross-checks

* `review_queue.csv`: 227 of 518 cases carry at least one flag (131 timing-only attribution, LOW; 91 audit record not
  found, 68 absence by coverage only, MEDIUM). None is HIGH in this dataset (every requester resolves and every subject
  has evidence). The queue is the honest counterpart of the confident-looking `output.csv`.
* `run_manifest.json`: input, code and output hashes of the run that produced `output.csv`.
* Blind run (`--no-sample-truth`): 14 of 518 rows differ from the default run, no status changes, so the dependence on
  the supplied sample answers is small.
* `python3 ghost_audit/evaluation/media_crosscheck.py`: the offline fallbacks (PDF text layer, tesseract) independently
  recover 11 of the 16 transcribed media resources with the same state and contradict none; the other five are
  images/PDFs with no readable resource id (scans, CID text) and stay on the human transcription.

## Policy-table coverage and packaging checks

* Four rule categories (`SECONDARY_IDENTIFIER`, `CACHE_ENTRY`, `PRODUCT_TELEMETRY`, `EMAIL_DELIVERY_LOG`) appear only
  as activity noise (368 email-send rows, 284 cache-refresh rows): no evidence file contains a resource id of those
  kinds, so no finding can cite evidence for them and the audit cannot report them. The rule engine still maps them, so
  evidence for them would be handled.
* `output.csv` is byte-identical on Python 3.9, 3.10, 3.11, 3.12 and 3.14.
* `./package_submission.sh` builds `code.zip` (62 files, no dataset, no nested archive, no cache) and
  `agent-trace.zip`; the unzipped `code.zip` reproduces `output.csv` byte for byte and passes all 19 evaluation cases.

## Robustness suite (`ghost_audit/evaluation/robustness.py`)

Row order of five input CSVs shuffled (2 seeds, different hash seeds): output byte-identical. Unparseable lines
appended to every log: output byte-identical. All PNG/PDF evidence removed from the manifest: run completes and the
strict validator passes. Windows re-calibrated from the data reproduce the same `output.csv`.

## Additional evaluation cases (`ghost_audit/evaluation/custom_cases.py`)

Each builds a tiny synthetic world, so the expected answer is known by construction.

1. **Non-deletion in another language:** a Spanish request to update a phone number and not close the account gives `NOT_APPLICABLE` with `[]`.
2. **Later evidence ignored and historical email resolved:** the request uses an old email; a search hit captured after `audit_at` must not change the answer, which stays `COMPLETE` and cites the earlier evidence.
3. **Replica drift plus active flow:** an account present only in a failover replica and an enabled data flow produce `INCOMPLETE`, with findings before remediation, `DISABLE_DATA_FLOW` before `DELETE_RECORD`, consecutive step numbers, and empty evidence on remediation and verification steps.
4. **Tombstone:** a tombstone that still holds name and email is redacted (`REDACT_RECORD`, `VERIFY_RECORD_REDACTED`) rather than deleted.
5. **Look-alike email:** a record for a similar address is not attributed to the subject.

6. **Model output is validated:** a mocked model reply containing a made-up resource id and an invalid state keeps only the valid resource, and the call's tokens are counted.
7. **Model cannot silently override intent:** a model "non-deletion" verdict on a plain deletion request is surfaced as a disagreement, not applied.
8. **Strict validator:** an empty `COMPLETE` array and an out-of-order step list are both rejected.

9. **Identity graph:** a historical email resolves to its user with the audit-log edge as rationale; a look-alike address resolves to nobody.
10. **Rules drive the plan:** a modified `deletion_rules.csv` changes the treatment of the affected categories only.
11. **Dependency check:** a plan that deletes before disabling a data flow is flagged; the canonical order is proven safe.
12. **Negative evidence:** absence is CONFIRMED (explicit negative), COVERED (system inspected by an earlier snapshot) or UNRESOLVED.

13. **Timestamps:** fractional seconds, offsets, space separators and date-only values normalise to one UTC form before any comparison.
14. **Unverifiable requester:** an email that matches no identity yields `NOT_APPLICABLE` with `[]` and a queue entry, never a success.
15. **No evidence at all:** a verified subject with no resources is not given an empty COMPLETE.
16. **Review queue:** a missing audit record is flagged `retention_unconfirmed`.
17. **Privacy:** emails, phones and hashes are masked before text reaches any model.
18. **Unknown rule action:** an unrecognised `required_action` is treated as RETAIN (no destruction on a guess).
19. **Offline PDF reading:** the text layer of a supplied PDF is read without any library or model.

All nineteen pass. The model-assisted path is tested only against mocked replies: no API key was available in the
development environment, so no live model call has been made and `usage_report.md` records 0 calls.

The sample run also prints an error taxonomy (missed audit record, tie swap, missed account, ...): on the samples it is 2 missed audit records, 2 tie swaps, 1 missed account.

`python3 ghost_audit/evaluation/main.py -v` prints a structural diff per imperfect sample case (missing / extra steps,
field mismatches, sequence verdict).

## Known limits

Resources with no identifier (deleted accounts, anonymized analytics) are attached by activity timing; when two
cases on the same day compete for the same kind of resource, the choice between them is arbitrary. Audit-record
IDs absent from every evidence file cannot be reported.
