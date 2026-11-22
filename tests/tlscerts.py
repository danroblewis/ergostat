"""Certificates for the mutual TLS tests, made with the ``openssl`` CLI once per session (``-extfile``, which OpenSSL
and macOS LibreSSL both take). A missing ``openssl`` fails the tests: it never skips them."""

import secrets
import shutil
import subprocess
from pathlib import Path

import pytest

CA_EXT = "basicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\n"
LEAF_EXT = ("basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
            "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\nextendedKeyUsage={use}\n"
            "subjectAltName={san}\n")


def _run(*args: str, cwd: Path) -> None:
    got = subprocess.run(["openssl", *args], cwd=cwd, capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, f"openssl {' '.join(args)}: {got.stderr}"


def _key(d: Path, name: str) -> Path:
    _run("genrsa", "-out", f"{name}.key", "2048", cwd=d)
    return d / f"{name}.key"


def _ca(d: Path, name: str) -> tuple[Path, Path]:
    key = _key(d, name)
    (d / f"{name}.ext").write_text(CA_EXT)
    _run("req", "-new", "-key", key.name, "-subj", f"/CN=ergostat test {name}", "-out", f"{name}.csr", cwd=d)
    _run("x509", "-req", "-in", f"{name}.csr", "-signkey", key.name, "-days", "3", "-sha256",
         "-set_serial", f"0x{secrets.token_hex(8)}", "-extfile", f"{name}.ext", "-out", f"{name}.pem", cwd=d)
    return d / f"{name}.pem", key


def _leaf(d: Path, name: str, ca: tuple[Path, Path], use: str, san: str) -> tuple[Path, Path]:
    key = _key(d, name)
    (d / f"{name}.ext").write_text(LEAF_EXT.format(use=use, san=san))
    _run("req", "-new", "-key", key.name, "-subj", f"/CN={name}", "-out", f"{name}.csr", cwd=d)
    _run("x509", "-req", "-in", f"{name}.csr", "-CA", str(ca[0]), "-CAkey", str(ca[1]), "-days", "3", "-sha256",
         "-set_serial", f"0x{secrets.token_hex(8)}", "-extfile", f"{name}.ext", "-out", f"{name}.pem", cwd=d)
    return d / f"{name}.pem", key


def make(d: Path) -> dict[str, Path]:
    assert shutil.which("openssl"), "the mutual TLS tests need the openssl command"
    ca, other = _ca(d, "ca"), _ca(d, "other-ca")
    server = _leaf(d, "server", ca, "serverAuth", "IP:127.0.0.1,DNS:localhost")
    wrong = _leaf(d, "wrong-server", ca, "serverAuth", "DNS:other.example")
    client = _leaf(d, "client", ca, "clientAuth", "DNS:client.example")
    stranger = _leaf(d, "stranger", other, "clientAuth", "DNS:stranger.example")
    return {"ca": ca[0], "other_ca": other[0], "server": server[0], "server_key": server[1], "wrong": wrong[0],
            "wrong_key": wrong[1], "client": client[0], "client_key": client[1], "stranger": stranger[0],
            "stranger_key": stranger[1]}


@pytest.fixture(scope="session")
def certs(tmp_path_factory) -> dict[str, Path]:
    return make(tmp_path_factory.mktemp("tls"))
