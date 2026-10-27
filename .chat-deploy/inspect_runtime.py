import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / '.chat-deploy'
FILES = (
    'mysite/api/booking_text.py', 'mysite/api/chat.py', 'mysite/api/chat_service.py',
    'mysite/api/travel_selection.py', 'mysite/chain/agent.py',
    'mysite/chain/prompts.py', 'mysite/chain/tools.py',
)
SSH = [
    'C:/Windows/System32/OpenSSH/ssh.exe', '-T', '-i',
    'C:/Users/user/.ssh/kyrgyzgo_ec2_deploy', '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=yes', '-o',
    'UserKnownHostsFile=C:/Users/user/.ssh/kyrgyzgo_github_known_hosts',
    '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15',
    'ubuntu@13.53.40.37',
]


def remote(command, **kwargs):
    return subprocess.run([*SSH, command], check=True, **kwargs)


if __name__ == '__main__':
    probe = '''import hashlib,json,os
from pathlib import Path
names = ['main.py', 'Dockerfile', 'requirements.txt', 'alembic.ini'] + %r
print(json.dumps({name: hashlib.sha256(Path('/app', name).read_bytes().replace(b'\\r\\n',b'\\n')).hexdigest() if Path('/app', name).is_file() else None for name in names}))
''' % list(FILES)
    result = remote('sudo -n docker exec kyrgyz_go-api-1 python -c ' + shlex.quote(probe), capture_output=True)
    manifest = json.loads(result.stdout)
    (TARGET / 'baseline-hashes.json').write_text(json.dumps(manifest, indent=2))
    fetch = '''import sys,tarfile
from pathlib import Path
with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz') as bundle:
    for name in %r:
        path = Path('/app', name)
        if path.is_file():
            bundle.add(path, arcname=name, recursive=False)
''' % list(FILES)
    result = remote('sudo -n docker exec kyrgyz_go-api-1 python -c ' + shlex.quote(fetch), capture_output=True)
    (TARGET / 'baseline.tar.gz').write_bytes(result.stdout)
    with tarfile.open(fileobj=io.BytesIO(result.stdout)) as bundle:
        bundle.extractall(TARGET / 'baseline', filter='data')
    for name in FILES:
        deployed = manifest[name]
        try:
            head = subprocess.check_output(['git', 'show', 'HEAD:' + name], cwd=ROOT)
            same_head = hashlib.sha256(head.replace(b'\r\n', b'\n')).hexdigest() == deployed
        except subprocess.CalledProcessError:
            same_head = False
        print(name + ': ' + ('matches HEAD' if same_head else 'DIFFERS from HEAD'))
    info = remote('sudo -n docker inspect kyrgyz_go-api-1', capture_output=True)
    container = json.loads(info.stdout)[0]
    safe_info = {
        'id': container['Id'], 'image_id': container['Image'],
        'image': container['Config']['Image'], 'state': container['State']['Status'],
        'health': container['State'].get('Health', {}).get('Status'),
        'working_dir': container['Config']['WorkingDir'],
        'mounts': [{'destination': x['Destination'], 'type': x['Type']} for x in container['Mounts']],
        'compose_project': container['Config']['Labels'].get('com.docker.compose.project'),
        'compose_service': container['Config']['Labels'].get('com.docker.compose.service'),
        'compose_files': container['Config']['Labels'].get('com.docker.compose.project.config_files'),
    }
    (TARGET / 'baseline-container.json').write_text(json.dumps(safe_info, indent=2))
    print(json.dumps(safe_info, indent=2))
