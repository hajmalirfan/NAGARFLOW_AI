"""A throwaway PostgreSQL cluster for tests and measurements.

    python scripts/throwaway_postgres.py start --dir PATH
    python scripts/throwaway_postgres.py createdb --dir PATH --name nagarflow_perf
    python scripts/throwaway_postgres.py stop --dir PATH

It never touches an installed PostgreSQL service. The generated password and
the connection URL are written into PATH, not printed.
"""

import argparse
import os
import secrets
import subprocess
from pathlib import Path

PG_BIN = Path(os.environ.get("PG_BIN", "C:/Program Files/PostgreSQL/18/bin"))
USER = "nagarflow"
PORT = 55432


def _run(tool: str, *args: str, password: str | None = None) -> None:
    env = {**os.environ, **({"PGPASSWORD": password} if password else {})}
    subprocess.run([str(PG_BIN / tool), *args], check=True, env=env)


def _password(folder: Path) -> str:
    return (folder / "password.txt").read_text().strip()


def url_for(folder: Path, name: str) -> str:
    return f"postgresql+psycopg://{USER}:{_password(folder)}@127.0.0.1:{PORT}/{name}"


def createdb(folder: Path, name: str) -> None:
    _run("createdb", "-h", "127.0.0.1", "-p", str(PORT), "-U", USER, name,
         password=_password(folder))
    (folder / f"{name}.url").write_text(url_for(folder, name))


def start(folder: Path) -> None:
    data = folder / "data"
    if not data.exists():
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "password.txt").write_text(secrets.token_urlsafe(24))
        _run("initdb", "-D", str(data), "-U", USER, f"--pwfile={folder / 'password.txt'}",
             "-A", "scram-sha-256", "-E", "UTF8")
        first_start = True
    else:
        first_start = False
    _run("pg_ctl", "-D", str(data), "-l", str(folder / "server.log"), "-w",
         "-o", f"-p {PORT} -c listen_addresses=127.0.0.1", "start")
    if first_start:
        createdb(folder, "nagarflow_test")


def stop(folder: Path) -> None:
    _run("pg_ctl", "-D", str(folder / "data"), "-m", "fast", "-w", "stop")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "stop", "createdb"])
    parser.add_argument("--dir", required=True)
    parser.add_argument("--name")
    options = parser.parse_args()
    folder = Path(options.dir).resolve()
    if options.command == "start":
        start(folder)
    elif options.command == "stop":
        stop(folder)
    else:
        createdb(folder, options.name)


if __name__ == "__main__":
    main()
