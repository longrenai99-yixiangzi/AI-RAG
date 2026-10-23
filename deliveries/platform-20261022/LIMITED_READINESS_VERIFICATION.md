# Current limited-trial readiness verification

Scope: an existing local, single-user design-management trial. This is not a formal service cutover, enterprise multi-user release, or whole-library business acceptance.

The overview no longer says continuous generation is unavailable while the approved bounded daily-answer policy is active. It explains that local verified answers remain local and language generation follows the current material, time, request and budget approval. No backend code or original index changed.

Verified in local Edge headless against the actual running entry:

- 21 browser checks covering navigation, material search and preview, question submission, expandable primary evidence, opening the original, history persistence, wrong-count rejection, narrow layout and creating a backup.
- The opened original's bytes matched the cited version. This did not visually verify the PDF page or establish document validity.
- The 390-pixel layout had no horizontal overflow. No foreground manual UI acceptance is claimed.
- The new backup and its internal file manifest passed verification. An isolated copy restored 82 question records and 10 generation-workflow records without replacing live state. There were no managed incremental files in this registry, so this phase does not claim to test missing-file restoration.
- Repeated startup preserved listener identities. Original source hashes, approval, expiry, old records and spending remained unchanged.
- A ten-minute observation sampled both services every 30 seconds; see publication-checks.json for the completed result. This does not establish long-term reliability, concurrency, or full-machine recovery.

TypeScript and the independent frontend build passed; served assets matched the build. The previous 615 backend checks remain the baseline and were not rerun for this copy-only UI change. This phase added zero real model HTTP calls, no parsing, document embeddings, or business-knowledge publication. Current daily usage remains 9/20 requests and CNY 0.60 conservatively reserved, with 11 requests left under the original expiry.

The local handoff now separates completed technical checks, two historical answers presented for business review, and three known content limitations. Missing template coverage, a missing aspect of a project case, and insufficient evidence remain explicit limitations. Historic answers are not silently converted into current-version or owner-approved acceptance.

Two initial harness errors were retained: a readiness-key assumption that did not match one service's response contract, and a browser assertion made before a submit button returned to its idle label. They were corrected before the complete reruns; neither is reported as a service outage.

Follow-up: the owner has now accepted both reviewed answers and their sources. [Acceptance scope](OWNER_ANSWER_ACCEPTANCE.md) records this decision separately from technical validation and overall system acceptance.
