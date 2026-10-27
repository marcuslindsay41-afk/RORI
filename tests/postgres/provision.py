"""Create an isolated disposable PostgreSQL fixture; never inspect application secrets.

Run: python tests/postgres/provision.py /tmp/rori-evidence-test.json
Requires Docker and postgres:15. Prints only the private config path.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time


def provision(destination):
    path = Path(destination).resolve()
    if path.exists():
        raise FileExistsError('Refusing to overwrite an existing test configuration')
    password = secrets.token_hex(32)
    container = 'rori-evidence-test-' + secrets.token_hex(6)
    environment = path.with_suffix('.docker-env')
    environment.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(environment, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(f'POSTGRES_PASSWORD={password}\nPOSTGRES_DB=rori_evidence_test\n')
        subprocess.run(['docker', 'run', '-d', '--name', container,
            '--tmpfs', '/var/lib/postgresql/data', '--env-file', str(environment),
            '-p', '127.0.0.1::5432', 'postgres:15'], check=True, capture_output=True)
        for _ in range(120):
            probe = subprocess.run(['docker', 'exec', container, 'pg_isready', '-h', '127.0.0.1', '-U', 'postgres',
                                    '-d', 'rori_evidence_test'], capture_output=True)
            if probe.returncode == 0:
                break
            time.sleep(.25)
        else:
            raise RuntimeError('Disposable PostgreSQL did not become ready')
        output = subprocess.run(['docker', 'port', container, '5432/tcp'], check=True,
                                capture_output=True, text=True).stdout.strip()
        port = int(output.rsplit(':', 1)[1])
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w') as stream:
            json.dump({'url': f'postgresql+psycopg2://postgres:{password}@127.0.0.1:{port}/rori_evidence_test',
                       'container': container}, stream)
    except BaseException:
        subprocess.run(['docker', 'rm', '-f', container], capture_output=True)
        raise
    finally:
        environment.unlink(missing_ok=True)
    print(f'Private test configuration created: {path}')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python tests/postgres/provision.py /tmp/unique-test-config.json')
    provision(sys.argv[1])
