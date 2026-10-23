# Explicit appendix outline retrieval

The existing complete-list route only recognized declared item/group enumerations. It returned no primary evidence for chapter-based appendix requests even when those pages were already indexed. The shared catalog now also reads an explicitly selected document and appendix's headings between adjacent appendix boundaries.

The implementation uses existing, admitted, version-bound PDF evidence. It checks page continuity, chapter sequence, source selection, appendix-title consistency and eligible evidence, and retains source page locations. It extracts chapter and subsection titles without parsing the original again or creating new document embeddings. No real appendix number, chapter count or business answer is hardcoded.

An indexed outline is not proof that every original paragraph or table field was parsed correctly. Requests also asking for content retain an explicit partial-answer gap for fields, examples and completion instructions. The local result must not be used by new or old model previews to invent those details. Pure outlines retain their structural-only limit and document-validity caveat.

Validation:

- Final exported backend snapshot: 627 passing checks, including 12 new tests; three existing dependency deprecation warnings.
- Synthetic three-chapter fixtures cover appendix boundaries, missing pages, conflicting chapter sequence, wrong appendix title, changed source bytes, modified audit data, ambiguous sources and old-preview spending protection.
- Eight live question variants and two final locator checks exercised distinct appendices, wrong names, additional responsibilities and previous list/personnel/amount routes. Fourteen technical question records include the initial harness attempt and repeated locator checks; this is not fourteen independent topics.
- A headless local Edge browser opened the final history result and expanded its primary reference. The output and the remaining detail gap were visible. No frontend source or build changed.
- Original source hashes, the candidate, historical records, current approval, expiry and spending were preserved. This phase added zero real model HTTP calls and did not publish business knowledge. Daily usage remains 9/20 requests and CNY 0.60 conservatively reserved under the existing approval.

Three content limitations remain, with the template limitation narrowed to detail extraction rather than inability to locate its chapter structure. This is not whole-library business acceptance, a new owner confirmation of the template answer, or formal-service deployment. Only the existing retrieval and daily-trial workers were reloaded; old entries and the formal service boundary were preserved.
