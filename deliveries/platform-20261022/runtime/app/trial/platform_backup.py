"""Verified local snapshots; paid-call ledgers are never restored or reset."""
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import uuid
import zipfile
from datetime import datetime, timezone

from .knowledge_store import _now
from .platform_generation import file_hash
from .platform_store import PlatformConflict


def create_backup(store, *, allow_missing=False):
    folder = store.path.parent / "backups"
    folder.mkdir(parents=True, exist_ok=True)
    key = uuid.uuid4().hex
    path = folder / (key + ".zip")
    def snapshot(state):
        saved=copy.deepcopy(state)
        contents = {}
        missing=[]
        root = store.path.parent.resolve()
        for job in saved["jobs"].values():
            for field in ("input_path", "package_path"):
                if not job.get(field):
                    continue
                item = Path(job[field]).resolve()
                if not item.is_relative_to(root / "runtime") or item.is_symlink():
                    raise ValueError("备份文件越界。")
                relative = item.relative_to(root).as_posix()
                if not relative.startswith(("runtime/files/", "runtime/index/")):
                    raise ValueError("备份仅包含受管文件与增量索引。")
                try:
                    contents[relative] = item.read_bytes()
                except FileNotFoundError:
                    if not allow_missing:raise
                    missing.append(relative)
                    job.update(status='FAILED',error='恢复前安全快照记录受管文件缺失，需重新入库：'+relative)
        contents['state.json']=json.dumps(saved,ensure_ascii=False).encode()
        manifest = {name: hashlib.sha256(data).hexdigest() for name,data in contents.items()}
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name,data in contents.items():
                archive.writestr(name,data)
            archive.writestr("manifest.json",json.dumps(manifest))
        return {"backup_id":key,"sha256":file_hash(path),"files":len(contents),"created_at":_now(),"path":str(path),"missing_files":missing}
    return store._mutate(snapshot)


def list_backups(store):
    folder=store.path.parent/'backups'
    return [{"backup_id":p.stem,"sha256":file_hash(p),"bytes":p.stat().st_size,"created_at":datetime.fromtimestamp(p.stat().st_mtime,timezone.utc).isoformat()} for p in sorted(folder.glob('*.zip'),key=lambda p:-p.stat().st_mtime) if len(p.stem)==32]


def restore_backup(store, backup_id, expected_hash, actor):
    if len(backup_id)!=32 or any(c not in '0123456789abcdef' for c in backup_id):
        raise ValueError("备份编号不合法。")
    archive_path=store.path.parent/'backups'/(backup_id+'.zip')
    if file_hash(archive_path)!=expected_hash:
        raise ValueError("备份文件校验失败。")
    with zipfile.ZipFile(archive_path) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)) or sum(i.file_size for i in archive.infolist())>512*1024*1024:
            raise ValueError("备份内容重复或超过恢复上限。")
        manifest=json.loads(archive.read('manifest.json'))
        if set(names)!={'manifest.json',*manifest}:
            raise ValueError("备份清单不一致。")
        contents={}
        for name,expected in manifest.items():
            relative=PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name or (name!='state.json' and not name.startswith(('runtime/files/','runtime/index/'))):
                raise ValueError("备份含越界路径。")
            data=archive.read(name)
            if hashlib.sha256(data).hexdigest()!=expected:
                raise ValueError("备份内容校验失败。")
            contents[name]=data
    restored=json.loads(contents['state.json'])
    if restored.get('platform_schema')!=1 or any(not isinstance(restored.get(k),dict) for k in ('sources','knowledge','candidates','jobs','query_runs','generations')):
        raise ValueError("备份状态格式不兼容。")
    # Refuse foreign absolute paths: an exported snapshot is not a portable arbitrary-file restore.
    root=store.path.parent.resolve()
    for job in restored['jobs'].values():
        for field in ('input_path','package_path'):
            if job.get(field) and not Path(job[field]).resolve().is_relative_to(root/'runtime'):
                raise ValueError("备份属于其他工作目录，请通过受控迁移处理。")
    if any(j['status'] in {'QUEUED','PROCESSING'} for j in store.snapshot()['jobs']):
        raise PlatformConflict("入库任务尚未结束，不能恢复。")
    if any(g['status']=='EXECUTING' for g in store.snapshot()['generations']):raise PlatformConflict('模型调用尚未结束，不能恢复。')
    # Preserve a damaged current state without making a missing file block recovery from a valid backup.
    safety=create_backup(store,allow_missing=True)
    def action(current):
        if any(j['status'] in {'QUEUED','PROCESSING'} for j in current['jobs'].values()):
            raise PlatformConflict("入库任务已变化，恢复已停止。")
        if any(g['status']=='EXECUTING' for g in current['generations'].values()):raise PlatformConflict('模型调用已开始，恢复已停止。')
        # Immutable files are restored individually; no recursive move/delete and no credential files.
        for name,data in contents.items():
            if name=='state.json':continue
            path=(root/name).resolve()
            if not path.is_relative_to(root/'runtime'):raise ValueError("恢复目标越界。")
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()!=manifest[name]:
                raise ValueError("受管文件内容已改变，拒绝覆盖。")
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():path.write_bytes(data)
        for key,value in current.get('generations',{}).items():
            restored['generations'][key]=value
            for run_id in {value.get('query_run_id') or 'QR_'+key,value.get('offline_replay_run_id')}:
                if run_id in current['query_runs']:restored['query_runs'][run_id]=copy.deepcopy(current['query_runs'][run_id])
        for job in restored['jobs'].values():
            if job['status'] in {'PROCESSING','QUEUED'}:job.update(status='INTERRUPTED',error='从备份恢复，需人工重试。')
        for run in restored['query_runs'].values():
            if run.get('status')=='RUNNING':run.update(status='INTERRUPTED')
        # A content backup must neither rewind spending nor restore an old external-call approval.
        restored.pop('daily_answer_policy',None)
        if 'daily_answer_policy' in current:
            restored['daily_answer_policy']=copy.deepcopy(current['daily_answer_policy'])
        current.clear();current.update(restored)
        store._event(current,'平台备份恢复',backup_id,actor,'恢复前安全快照：'+safety['backup_id'])
        return {'restored':True,'safety_backup_id':safety['backup_id'],'safety_missing_files':safety['missing_files'],'paid_call_ledgers_restored':False}
    return store._mutate(action)
