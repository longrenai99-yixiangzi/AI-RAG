# V2.6 Live Shadow Lost Hit Root-Cause Diagnosis

- Captured: `2026-09-14T11:43:15.441279+08:00`
- Boundary: frozen V2.5 unchanged; 8000 untouched; 8010 not switched.

## LSR-014

- Root cause: `SOURCE_BODY_MISSING`
- Finding: V2.5 only contains a registration/index page that names the PDF; the PDF body is absent from the frozen candidate staging corpus.
- Remediation: Ingest the real PDF as a V2.6.1_DEV_REMEDIATION source, then replay Q74; do not rewrite frozen V2.5.

- Physical source: `D:\工作\二公司技术部\2026\局优秀管理经验\04.中建三局项目数字建造系统解决方案.pdf`; exists=`True`; parse=`parsed`; SHA-256=`e51a58bc0a5865620202c0ef39a0597b1e0e3853f48007647dec496121a0b176`.

## LSR-017

- Root cause: `TEMPORAL_SCOPE_COLLISION`
- Finding: The query specifies 2025 H1, but conflict detection groups H1 3.31% with full-year 3.33% because the plan has year but no period scope.
- Remediation: Add H1/FULL_YEAR period scope to query plans and evidence; compare numeric facts only inside the same period, while retaining conflicts for period-unspecified queries.

- Scope: H1=3.31%; full year=3.33%; these are different periods and must not be treated as a same-period conflict.
