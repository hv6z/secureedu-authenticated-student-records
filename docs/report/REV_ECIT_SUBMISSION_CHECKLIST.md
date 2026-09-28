# REV-ECIT 2026 — revision record and submission checklist

## 1. Reviewer issues and implemented responses

| FAIR 2026 issue | Implemented response | Evidence |
|---|---|---|
| Public SHA-256 chain could be rebuilt by a database writer | Added a domain-separated HMAC-SHA-256 to every audit block | `src/integrity/audit.py`, block schema 3 |
| Chain head lived in attacker-controlled SQLite | Added an authenticated chain-head checkpoint outside SQLite and fail-closed startup | `*.audit-anchor.json`, `RecordService.initialize()` |
| Mutation tests only changed bytes without repairing dependent state | Added seven adaptive database-writer transformations: modify/re-hash, timestamp/re-hash, delete/rechain, suffix truncation/head repair, splicing, reorder/reindex, and partial rollback | `tamper_summary_20260925T065010Z.csv`: 210/210 adaptive cases rejected |
| “360/360” could be misread as an attack-detection probability | Revised paper explicitly describes the result as deterministic implementation coverage under a key-separation assumption | Sections V–VII of the manuscript |
| No independent baseline | Added SQLCipher 4.12 Community with raw 256-bit key, WAL, and `cipher_integrity_check`, repeated 10 times at all three sizes | `summary_20260927T033437Z.csv` |
| Prior measurements used an unsuitable/unclear storage environment | New runs use the persistent Windows filesystem; metadata records OS, CPU, RAM, Python, SQLite, packages, commit, and source hash | `metadata_rev_ecit_20260927.json` and component metadata files |
| No multi-writer evaluation | Added 1/2/4/8-thread contention experiment, 120 records, 10 repetitions; added a shared in-process write lock spanning database commit and checkpoint refresh | `contention_summary_20260927T031003Z.csv` |
| Scientific contribution was overstated | Removed distributed-blockchain/immutability claims; contribution is now a threat-driven composition and falsifiable evaluation of standard mechanisms | Title, abstract, introduction, limitations, conclusion |
| Related work focused too heavily on educational blockchain | Added SQLCipher, Schneier–Kelsey secure logs, Crosby–Wallach tamper-evident logs, and Certificate Transparency | Section II and Table I |

## 2. Verified technical state

- Repository: `https://github.com/hv6z/secureedu-authenticated-student-records`
- Revision branch and `main`: commit `4886947`
- Automated tests: 118/118 passed
- Statement coverage: 90.90%
- Tamper experiment: 390/390 generated states rejected across 13 operators
- Independent baseline: SQLCipher 4.12.0 Community (`sqlcipher3==0.6.2`)
- Writer contention: 1, 2, 4, and 8 threads; 10 repetitions per level
- Manuscript: 4 A4 pages, below the six-page REV-ECIT limit
- Final page render inspected: no clipping, overlap, unintended blank page, or stale template text
- Official template SHA-256 remained unchanged: `19DCD2E8A6183A2674961ADACB58C784B52A1FF0BF364C60D0CD16929E18EC60`

## 3. Files to use

- Submission Word file: `docs/report/SecureEdu_REV_ECIT_2026.docx`
- Submission PDF/check copy: `docs/report/SecureEdu_REV_ECIT_2026.pdf`
- Editable source: `docs/report/REV_ECIT_2026_manuscript.md`
- Official retained template: `docs/report/REV-ECIT_official_template.docx`
- Rebuild script: `scripts/build_rev_ecit_paper.py`
- Combined performance data: `experiments/results/raw_rev_ecit_20260927.csv`
- Combined statistics: `experiments/results/summary_rev_ecit_20260927.csv`
- Result provenance: `experiments/results/metadata_rev_ecit_20260927.json`

## 4. Author decisions still required before submission

- [ ] Confirm whether Trần Thị Hà Vy is the sole author.
- [ ] If not, provide every co-author’s exact name, affiliation, email, and author order.
- [ ] Identify the corresponding author and provide ORCID identifiers if used.
- [ ] Decide whether the adviser is a co-author or appears only in Acknowledgment.
- [ ] Replace both bold square-bracket placeholders in the Word/PDF manuscript.
- [ ] Confirm funding and conflict-of-interest statements required by the submission form.
- [ ] Confirm the paper title and author order exactly match the EasyChair metadata.

## 5. Final submission checks

- [ ] Run an authorized similarity report and keep the total below the conference threshold; inspect source-by-source overlap rather than relying only on the total percentage.
- [ ] Recheck every citation, DOI, author name, year, and access date.
- [ ] Open the final Word file on the computer used for submission and confirm fonts/equations did not reflow.
- [ ] Export the final PDF after author metadata is filled and confirm it remains at most six A4 pages.
- [ ] Remove comments, tracked changes, document properties that should not be disclosed, and temporary placeholders.
- [ ] Upload only the final file requested by REV-ECIT and verify the downloaded copy after submission.
- [ ] Preserve the EasyChair confirmation email and submitted-file checksum.

## 6. Claims that must not be added back

- Do not call SecureEdu a distributed blockchain or claim consensus/immutability.
- Do not claim protection if the attacker controls the master key and checkpoint.
- Do not describe 390/390 as a probability of detecting arbitrary attacks.
- Do not call the SQLCipher comparison functionally equivalent; it is an independent page-encryption baseline without SecureEdu’s history semantics.
- Do not claim production readiness while crash recovery, multi-process coordination, managed keys, HTTPS termination, and retention policy remain unimplemented.
