"""Deploy exactly seven chat files over the existing production image."""
import ast
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

from inspect_runtime import FILES, ROOT, TARGET, remote


REMOTE_SCRIPT = r'''
import fcntl, hashlib, io, json, os, shutil, subprocess, sys, tarfile, urllib.request
from pathlib import Path

spec = json.loads(SPEC_JSON)
files = spec['files']
root = Path('/home/ubuntu/Kyrgyz_Go')
release = Path('/home/ubuntu/releases') / spec['stamp']
backup = Path('/home/ubuntu/kyrgyzgo-backups') / spec['stamp']

def run(args, **kw):
    return subprocess.run(args, check=True, **kw)

def output(args):
    return subprocess.check_output(args, text=True).strip()

def inspect(name):
    return json.loads(output(['sudo', '-n', 'docker', 'inspect', name]))[0]

def manifest(container):
    code = """import hashlib,json
from pathlib import Path
root=Path('/app')
result={}
for path in root.rglob('*'):
    if not path.is_file(): continue
    rel=path.relative_to(root)
    if any(part=='__pycache__' or part.startswith('.env') for part in rel.parts): continue
    if path.suffix in {'.pyc','.pyo','.db','.sqlite','.sqlite3'}: continue
    result[rel.as_posix()]=hashlib.sha256(path.read_bytes().replace(bytes((13,10)),bytes((10,)))).hexdigest()
print(json.dumps(result))
"""
    return json.loads(output(['sudo','-n','docker','exec',container,'python','-c',code]))

os.umask(0o077)
with Path('/home/ubuntu/.kyrgyzgo-deploy.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    current = inspect('kyrgyz_go-api-1')
    if current['Id'] != spec['container_id'] or current['Image'] != spec['image_id']:
        raise RuntimeError('Active deployment changed; refusing to overwrite it')
    if current['State']['Health']['Status'] != 'healthy':
        raise RuntimeError('Existing API is unhealthy')
    if current['Mounts']:
        raise RuntimeError('Unexpected application mounts')
    before = manifest('kyrgyz_go-api-1')
    for name in files:
        if before.get(name) != spec['baseline'][name]:
            raise RuntimeError('Runtime file changed: ' + name)
    if shutil.disk_usage('/home/ubuntu/releases').free < 150 * 1024 * 1024:
        raise RuntimeError('Insufficient space for the small chat-only image layer')
    other_names = ('kyrgyzgo_postgres', 'kyrgyzgo_redis', 'kyrgyzgo_https')
    other_ids = {name: inspect(name)['Id'] for name in other_names}
    configs = current['Config']['Labels']['com.docker.compose.project.config_files'].split(',')
    if configs != [str(root / 'docker-compose.yml'), '/tmp/kyrgyzgo-api-network.yml']:
        raise RuntimeError('Unexpected Compose files')
    compose = ['sudo','-n','docker','compose','-p','kyrgyz_go']
    for name in configs:
        compose += ['-f', name]
    run([*compose,'config','--quiet'], cwd=root)
    release.mkdir()
    backup.mkdir()
    content = sys.stdin.buffer.read(2 * 1024 * 1024 + 1)
    if len(content) > 2 * 1024 * 1024:
        raise RuntimeError('Unexpectedly large chat archive')
    with tarfile.open(fileobj=io.BytesIO(content)) as bundle:
        members = bundle.getmembers()
        if sorted(x.name for x in members) != sorted([*files,'Dockerfile.chat']):
            raise RuntimeError('Archive contains files outside approved chat update')
        if any(not x.isfile() for x in members):
            raise RuntimeError('Only regular files are accepted')
        bundle.extractall(release, members=members, filter='data')
    for name in files:
        actual=hashlib.sha256((release/name).read_bytes().replace(bytes((13,10)),bytes((10,)))).hexdigest()
        if actual != spec['updated'][name]:
            raise RuntimeError('Uploaded file checksum mismatch: '+name)
    state = {'status':'preparing', 'previous_image':current['Image'],
             'changed_files':files, 'image':spec['image'], 'backup_image':spec['backup_image']}
    state_path = backup / 'deployment-state.json'
    state_path.write_text(json.dumps(state, indent=2))
    (backup/'runtime-before.json').write_text(json.dumps(before,indent=2))
    run(['sudo','-n','docker','tag',current['Image'],spec['backup_image']])
    run(['sudo','-n','docker','build','--network=none','-f',str(release/'Dockerfile.chat'),
         '-t',spec['image'],str(release)])
    smoke = """import ast
from pathlib import Path
for path in Path('/app/mysite').rglob('*.py'): ast.parse(path.read_text(encoding='utf-8-sig'))
import main
from mysite.api.booking_text import preview_text
from mysite.api.chat_service import public_preview
from mysite.chain.agent import confirmation_allowed
from mysite.chain.prompts import SELECTION_PROMPT
data={'client_name':'Test','phone':'+996700000001','notes':'Hidden','budget':'500 USD'}
assert preview_text(data,None)==chr(10).join(['Проверьте заявку:','Имя: Test','Телефон: +996700000001'])
assert public_preview({'data':data})['data']=={'client_name':'Test','phone':'+996700000001'}
assert confirmation_allowed('awaiting_confirmation','Отправить менеджеру')
assert not confirmation_allowed('consultation','Отправить менеджеру')
assert len(SELECTION_PROMPT)<5000
print('Candidate imports, syntax and chat contract: OK')
"""
    run(['sudo','-n','docker','run','--rm','--network','none','--env-file',str(root/'.env'),
         '--entrypoint','python',spec['image'],'-B','-c',smoke])
    state['status']='activating'
    state_path.write_text(json.dumps(state,indent=2))
    try:
        run(['sudo','-n','docker','tag',spec['image'],'kyrgyzgo-api:local'])
        run([*compose,'up','-d','--no-deps','--no-build','--wait','--wait-timeout','180','api'],cwd=root)
        active=inspect('kyrgyz_go-api-1')
        expected_image=output(['sudo','-n','docker','image','inspect',spec['image'],'--format={{.Id}}'])
        if active['Image'] != expected_image or active['State']['Health']['Status']!='healthy':
            raise RuntimeError('New API did not become healthy')
        after=manifest('kyrgyz_go-api-1')
        changed=sorted(name for name in set(before)|set(after) if before.get(name)!=after.get(name))
        if changed != sorted(files):
            raise RuntimeError('Unexpected runtime changes: '+repr(changed))
        for name in files:
            if after[name]!=spec['updated'][name]:
                raise RuntimeError('Deployed checksum mismatch: '+name)
        for name, container_id in other_ids.items():
            if inspect(name)['Id']!=container_id:
                raise RuntimeError('An unrelated service was recreated: '+name)
        for path in ('/', '/contacts/', '/openapi.json'):
            with urllib.request.urlopen('https://13.53.40.37'+path, timeout=30) as response:
                if response.status!=200: raise RuntimeError('HTTPS failed for '+path)
        state.update(status='healthy', image_id=active['Image'],container_id=active['Id'])
        (backup/'runtime-after.json').write_text(json.dumps(after,indent=2))
        print('VERIFIED: exactly seven approved chat files changed; other application files and service containers unchanged.',flush=True)
    except BaseException:
        state['status']='rolling_back'
        state_path.write_text(json.dumps(state,indent=2))
        run(['sudo','-n','docker','tag',current['Image'],'kyrgyzgo-api:local'])
        run([*compose,'up','-d','--no-deps','--no-build','--wait','--wait-timeout','180','api'],cwd=root)
        state['status']='rolled_back'
        raise
    finally:
        state_path.write_text(json.dumps(state,indent=2))
    print('CHAT_DEPLOYED '+spec['stamp'],flush=True)
'''


def main():
    baseline = json.loads((TARGET / 'baseline-hashes.json').read_text())
    container = json.loads((TARGET / 'baseline-container.json').read_text())
    stamp = 'chat-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    updated = {}
    contents = {}
    for name in FILES:
        data = (ROOT / name).read_bytes().replace(b'\r\n', b'\n')
        ast.parse(data.decode('utf-8-sig'), filename=name)
        contents[name] = data
        updated[name] = hashlib.sha256(data).hexdigest()
    spec = dict(files=list(FILES), stamp=stamp, baseline=baseline, updated=updated,
                container_id=container['id'], image_id=container['image_id'],
                image='kyrgyzgo-api:' + stamp, backup_image='kyrgyzgo-api:before-' + stamp)
    contents['Dockerfile.chat'] = (
        'FROM ' + spec['backup_image'] + '\nCOPY --chown=app:app mysite/ /app/mysite/\n'
    ).encode()
    archive = TARGET / (stamp + '.tar.gz')
    with tarfile.open(archive, 'w:gz') as bundle:
        for name, data in contents.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o644
            bundle.addfile(info, io.BytesIO(data))
    (TARGET / 'deployment-spec.json').write_text(json.dumps(spec, indent=2))
    code = REMOTE_SCRIPT.replace('SPEC_JSON', repr(json.dumps(spec)), 1)
    with archive.open('rb') as source:
        remote('python3 -c ' + shlex.quote(code), stdin=source)


if __name__ == '__main__':
    main()
