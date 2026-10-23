import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows operation entry')
@pytest.mark.parametrize('ready', [True, False])
def test_status_snapshots_preserve_success_or_failure_without_business_payload(tmp_path, ready):
    scripts = tmp_path/'scripts'
    scripts.mkdir()
    source = Path(__file__).resolve().parents[1]/'scripts/manage_platform.ps1'
    shutil.copyfile(source, scripts/source.name)
    trial = tmp_path/'evaluation/concise_trial_20261022'
    trial.mkdir(parents=True)
    prepared = trial/'prepared.json'
    prepared.write_text(json.dumps({'candidate_hash':'fixture'}), encoding='utf-8')
    wrapper = tmp_path/'exercise.ps1'
    wrapper.write_text(r'''
$fixtureRoot=$PSScriptRoot
function Get-CimInstance {
    [pscustomobject]@{Name='python.exe';ProcessId=123;ParentProcessId=0;ExecutablePath=(Join-Path $fixtureRoot '.venv/Scripts/python.exe');CommandLine='python.exe -m uvicorn app.trial.concise_trial:trial_app --host 127.0.0.1 --port 8897 --workers 1';CreationDate=(Get-Date)}
}
function Get-NetTCPConnection { [pscustomobject]@{OwningProcess=123} }
function Invoke-RestMethod {
    param($Uri,$TimeoutSec)
    if ($Uri -like '*8894/api/v2/unified/status') { return [pscustomobject]@{candidate_hash='fixture';sources=7;records=20;model_http_enabled=$false} }
    if ($Uri -notlike '*8897/api/platform/state') { throw 'Unexpected network endpoint' }
    return [pscustomobject]@{runtime=[pscustomobject]@{candidate_hash='fixture';ready=READY_VALUE};mode='EXISTING_CONTENT_TRIAL';capabilities=[pscustomobject]@{generation_execution_enabled=$false};daily_model=[pscustomobject]@{active=$false;policy_sha256='approved-fixture';material_count=6;used_requests=2;max_requests=20;reserved_cny=0.2;max_budget_cny=10;expires_at='2030-01-01T00:00:00+00:00';api_key='PRIVATE_SENTINEL'};runs=@([pscustomobject]@{question='PRIVATE_SENTINEL'})}
}
& (Join-Path $fixtureRoot 'scripts/manage_platform.ps1') -Action Status
'''.replace('READY_VALUE','$true' if ready else '$false'), encoding='utf-8-sig')
    previous = {}
    for index in range(2):
        result = subprocess.run(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(wrapper)],
                                capture_output=True, timeout=30)
        assert (result.returncode == 0) is ready, result.stderr.decode(errors='replace')
        records = list((trial/'health').glob('*.json'))
        assert len(records) == index+1
        for p in records:
            raw = p.read_bytes()
            if p in previous: assert raw == previous[p]
            previous[p] = raw
            row = json.loads(raw.decode('utf-8-sig'))
            assert row['schema_version'] == 1 and row['checked_at']
            assert row['result'] == ('READY' if ready else 'NOT_READY')
            assert 'PRIVATE_SENTINEL' not in raw.decode('utf-8-sig')
            if ready:
                assert row['daily_model']['used_requests'] == 2
                assert row['recent_questions_shown'] == 1
            else:
                assert row['failure_kind'] and 'daily_model' not in row
    assert json.loads(prepared.read_text()) == {'candidate_hash':'fixture'}
    assert not list(trial.rglob('*.zip'))
