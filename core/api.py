"""
kontainy — Motor API istemcisi
====================================

Podman'ın soketi Docker Engine API v1.41 ile uyumludur; bu yüzden tek bir
istemci her iki motoru da konuşur. Ayrım, bağlanılan endpoint'in `/version`
yanıtındaki `Components[].Name` alanından yapılır.

CLI çıktısı ayrıştırılmaz — soket üzerinden doğrudan JSON okunur.
Harici bağımlılık yoktur (docker-py, requests gerekmez).
"""

from __future__ import annotations

import http.client
import json
import socket
import ssl
import urllib.parse
from dataclasses import dataclass
from typing import Any, Iterator, Optional


class EngineError(Exception):
    """Motorla konuşurken oluşan her hata."""


# ---------------------------------------------------------------------------
#  Taşıma katmanı
# ---------------------------------------------------------------------------
class UnixHTTPConnection(http.client.HTTPConnection):
    """UNIX alan soketi üzerinden HTTP."""

    def __init__(self, socket_path: str, timeout: float = 10.0):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.socket_path)
        except OSError as exc:
            sock.close()
            raise EngineError(f"{self.socket_path}: {exc}") from exc
        self.sock = sock


def _connection(endpoint: str, timeout: float):
    """Endpoint dizgisinden uygun HTTP bağlantısını üretir.

    Desteklenen biçimler:
        unix:///run/podman/podman.sock
        /run/docker.sock                  (çıplak yol da kabul edilir)
        tcp://10.0.0.5:2375
        ssh://user@host                   (desteklenmez — açık hata verilir)
    """
    if endpoint.startswith("/"):
        return UnixHTTPConnection(endpoint, timeout)

    parsed = urllib.parse.urlparse(endpoint)
    scheme = parsed.scheme

    if scheme in ("unix", "http+unix"):
        return UnixHTTPConnection(parsed.path, timeout)

    if scheme in ("tcp", "http"):
        return http.client.HTTPConnection(parsed.hostname, parsed.port or 2375,
                                          timeout=timeout)

    if scheme == "https":
        return http.client.HTTPSConnection(parsed.hostname, parsed.port or 2376,
                                           timeout=timeout,
                                           context=ssl.create_default_context())

    if scheme == "ssh":
        raise EngineError("ssh:// hedefleri henüz desteklenmiyor")

    raise EngineError(f"Bilinmeyen endpoint biçimi: {endpoint}")


# ---------------------------------------------------------------------------
#  İstemci
# ---------------------------------------------------------------------------
@dataclass
class EngineInfo:
    kind: str            # "docker" | "podman" | "unknown"
    version: str
    api_version: str
    os: str
    arch: str
    rootless: bool
    raw: dict


class EngineClient:
    """Docker Engine API uyumlu tek bir endpoint'e bağlanır."""

    API = "v1.41"   # Podman'ın taahhüt ettiği uyumluluk seviyesi

    def __init__(self, endpoint: str, label: str = "", timeout: float = 10.0):
        self.endpoint = endpoint
        self.label = label or endpoint
        self.timeout = timeout

    # --- alt seviye -------------------------------------------------------
    def _request(self, method: str, path: str, *, params: dict = None,
                 body: Any = None, stream: bool = False):
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            if clean:
                path = f"{path}?{urllib.parse.urlencode(clean)}"

        conn = _connection(self.endpoint, self.timeout)
        headers = {"Host": "kontainy", "Accept": "application/json"}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"

        try:
            conn.request(method, f"/{self.API}{path}", body=payload, headers=headers)
            response = conn.getresponse()
        except EngineError:
            conn.close()
            raise
        except Exception as exc:
            conn.close()
            raise EngineError(f"{self.label}: {exc}") from exc

        if stream:
            return conn, response

        try:
            data = response.read()
        finally:
            conn.close()

        if response.status >= 400:
            detail = data.decode(errors="replace")[:300]
            raise EngineError(f"{self.label}: HTTP {response.status} — {detail}")

        if not data:
            return None
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return data.decode(errors="replace")

    # --- yüksek seviye ----------------------------------------------------
    def ping(self) -> bool:
        try:
            self._request("GET", "/_ping")
            return True
        except EngineError:
            return False

    def identify(self) -> EngineInfo:
        """Bu endpoint'in arkasında hangi motorun olduğunu belirler."""
        v = self._request("GET", "/version") or {}
        kind = "docker"
        for comp in v.get("Components", []) or []:
            if "podman" in str(comp.get("Name", "")).lower():
                kind = "podman"
                break
        else:
            if "podman" in str(v.get("Platform", {}).get("Name", "")).lower():
                kind = "podman"

        rootless = False
        try:
            info = self._request("GET", "/info") or {}
            if kind == "podman":
                rootless = bool(info.get("host", {}).get("security", {})
                                .get("rootless", False))
            else:
                rootless = "rootless" in (info.get("SecurityOptions") or [""])[0].lower() \
                    if info.get("SecurityOptions") else False
        except EngineError:
            info = {}

        return EngineInfo(
            kind=kind,
            version=v.get("Version", "?"),
            api_version=v.get("ApiVersion", "?"),
            os=v.get("Os", "?"),
            arch=v.get("Arch", "?"),
            rootless=rootless,
            raw={"version": v, "info": info},
        )

    def info(self) -> dict:
        return self._request("GET", "/info") or {}

    def containers(self, all_: bool = True) -> list:
        return self._request("GET", "/containers/json",
                             params={"all": "true" if all_ else "false"}) or []

    def images(self) -> list:
        return self._request("GET", "/images/json") or []

    def volumes(self) -> dict:
        return self._request("GET", "/volumes") or {}

    def networks(self) -> list:
        return self._request("GET", "/networks") or []

    def disk_usage(self) -> dict:
        return self._request("GET", "/system/df") or {}

    def inspect(self, container_id: str) -> dict:
        return self._request("GET", f"/containers/{container_id}/json") or {}

    def start(self, container_id: str) -> None:
        self._request("POST", f"/containers/{container_id}/start")

    def stop(self, container_id: str, timeout: int = 10) -> None:
        self._request("POST", f"/containers/{container_id}/stop",
                      params={"t": timeout})

    def restart(self, container_id: str, timeout: int = 10) -> None:
        self._request("POST", f"/containers/{container_id}/restart",
                      params={"t": timeout})

    def remove(self, container_id: str, force: bool = False,
               volumes: bool = False) -> None:
        self._request("DELETE", f"/containers/{container_id}",
                      params={"force": str(force).lower(),
                              "v": str(volumes).lower()})

    # --- akışlar ----------------------------------------------------------
    def logs(self, container_id: str, tail: int = 200) -> str:
        """Container loglarını okur.

        TTY'siz container'larda akış çoklanmıştır: her kare 8 baytlık bir
        başlıkla gelir (1 bayt akış türü, 3 bayt dolgu, 4 bayt uzunluk).
        Ham okunursa çıktıda çöp karakterler görünür — burada çözülür.
        """
        conn, response = self._request(
            "GET", f"/containers/{container_id}/logs",
            params={"stdout": "true", "stderr": "true", "tail": tail},
            stream=True)
        try:
            raw = response.read()
        finally:
            conn.close()
        return _demultiplex(raw)

    def events(self, filters: dict = None) -> Iterator[dict]:
        """Motorun olay akışını üretir. Yoklama yerine bu kullanılır."""
        params = {}
        if filters:
            params["filters"] = json.dumps(filters)
        conn, response = self._request("GET", "/events", params=params, stream=True)
        try:
            buffer = b""
            while True:
                chunk = response.read(1)
                if not chunk:
                    break
                buffer += chunk
                if chunk == b"\n":
                    line = buffer.strip()
                    buffer = b""
                    if line:
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue
        finally:
            conn.close()


def _demultiplex(raw: bytes) -> str:
    """Docker'ın çoklanmış log akışını düz metne çevirir."""
    if not raw:
        return ""
    # TTY'li container'larda başlık yoktur; ilk bayt 0-2 aralığında değilse düz metindir.
    if raw[0] not in (0, 1, 2):
        return raw.decode(errors="replace")

    out, i = [], 0
    while i + 8 <= len(raw):
        size = int.from_bytes(raw[i + 4:i + 8], "big")
        i += 8
        out.append(raw[i:i + size].decode(errors="replace"))
        i += size
    if i < len(raw):
        out.append(raw[i:].decode(errors="replace"))
    return "".join(out)
