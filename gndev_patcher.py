#!/usr/bin/env python3
"""
GnDev Patch Engine

Uso autorizado únicamente sobre APK propias o sobre las que tengas permiso.

Funciones:
- Descarga una APK desde URL directa o usa una APK local.
- Descompila con Apktool.
- Lee un ZIP de parche que contenga patch.txt.
- Ejecuta bloques [ADD_FILES] y [MATCH_REPLACE].
- Puede extraer ZIP internos dentro del proyecto descompilado.
- Elimina todas las directivas .line antes de aplicar el parche.
- Aplica los archivos y reemplazos después de limpiar los Smali.
- Recompila automáticamente con Apktool.
- Genera un reporte de ejecución.

Ejemplos:
    # Modo automático: descarga el APK oficial y usa GenOsPatch.zip
    python3 gndev_patcher.py

    # URL directa personalizada
    python3 gndev_patcher.py --apk-url "https://servidor/app.apk"

    # APK local
    python3 gndev_patcher.py --apk "WhatsApp.apk"
"""

from __future__ import annotations

import argparse
from html import unescape
from html.parser import HTMLParser
import fnmatch
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from http.cookiejar import CookieJar
from urllib.parse import urljoin, urlparse
from urllib.request import (
    HTTPCookieProcessor,
    Request,
    build_opener,
    urlopen,
)
import zipfile


ENGINE_VERSION = 3
OPERATION_TAGS = {"ADD_FILES", "MATCH_REPLACE"}

WHATSAPP_ANDROID_PAGE = "https://www.whatsapp.com/android"


def display_engine_banner(
    script_author: str = "GenOs",
    youtube_channel: str = "https://youtube.com/@Geniousmods",
) -> None:
    banner = r"""
   ██████╗ ███╗   ██╗██████╗ ███████╗██╗   ██╗
  ██╔════╝ ████╗  ██║██╔══██╗██╔════╝██║   ██║
  ██║  ███╗██╔██╗ ██║██║  ██║█████╗  ██║   ██║
  ██║   ██║██║╚██╗██║██║  ██║██╔══╝  ╚██╗ ██╔╝
  ╚██████╔╝██║ ╚████║██████╔╝███████╗ ╚████╔╝
   ╚═════╝ ╚═╝  ╚═══╝╚═════╝ ╚══════╝  ╚═══╝

              GNDEV PATCH ENGINE v1
    """
    log(banner.rstrip())
    log(f"  Autor del script: {script_author}")
    log(f"  Canal de YouTube: {youtube_channel}")
    log("  Descarga → hashes DEX → descompila → elimina .line → parchea → compila")
    log("=" * 66)


class OfficialWhatsAppAPKParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        for name, value in attrs:
            if name.lower() != "href" or not value:
                continue

            candidate = unescape(value).replace(r"\u0026", "&")
            lowered = candidate.lower()

            if ".apk" in lowered and (
                "scontent.whatsapp.net" in lowered
                or "whatsapp.com" in lowered
            ):
                self.urls.append(candidate)


def resolve_official_whatsapp_apk_url() -> str:
    """
    Obtiene el enlace directo vigente del APK desde la página oficial.

    Esta implementación replica exactamente el método probado manualmente:
    HTMLParser + urllib.request + filtro scontent.whatsapp.net + .apk.
    """
    page = WHATSAPP_ANDROID_PAGE
    request = Request(page, headers={"User-Agent": "Mozilla/5.0"})

    try:
        html = urlopen(request, timeout=60).read().decode(
            "utf-8",
            errors="ignore",
        )
    except HTTPError as exc:
        raise PatchError(
            f"No se pudo consultar la página oficial: HTTP {exc.code}."
        ) from exc
    except (URLError, TimeoutError) as exc:
        reason = getattr(exc, "reason", str(exc))
        raise PatchError(
            f"No se pudo consultar la página oficial: {reason}"
        ) from exc

    class APKParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.url: str | None = None

        def handle_starttag(
            self,
            tag: str,
            attrs: list[tuple[str, str | None]],
        ) -> None:
            for name, value in attrs:
                if name == "href" and value:
                    value = unescape(value)
                    if (
                        "scontent.whatsapp.net" in value
                        and ".apk" in value
                    ):
                        self.url = value

    parser = APKParser()
    parser.feed(html)

    if not parser.url:
        raise PatchError(
            "No se encontró el enlace directo del APK oficial."
        )

    return parser.url


class PatchError(RuntimeError):
    pass


def log(message: str = "") -> None:
    print(message, flush=True)


def hash_file(path: Path, algorithm: str) -> str:
    try:
        digest = hashlib.new(algorithm)
    except ValueError as exc:
        raise PatchError(f"Algoritmo hash no soportado: {algorithm}") from exc

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    return hash_file(path, "sha256")


def md5_file(path: Path) -> str:
    # MD5 se usa aquí únicamente como identificador/comparación, no como
    # garantía criptográfica de integridad.
    return hash_file(path, "md5")


def format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def dex_sort_key(name: str) -> tuple[int, str]:
    match = re.fullmatch(r"classes(\d*)\.dex", Path(name).name)
    if not match:
        return (10**9, name)
    suffix = match.group(1)
    return (1 if suffix == "" else int(suffix), name)


def hash_zip_entry(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> dict[str, Any]:
    md5_digest = hashlib.md5()
    sha256_digest = hashlib.sha256()

    with archive.open(info, "r") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5_digest.update(chunk)
            sha256_digest.update(chunk)

    return {
        "name": info.filename,
        "size_bytes": info.file_size,
        "size_human": format_bytes(info.file_size),
        "compressed_size_bytes": info.compress_size,
        "compressed_size_human": format_bytes(info.compress_size),
        "crc32": f"{info.CRC:08x}",
        "md5": md5_digest.hexdigest(),
        "sha256": sha256_digest.hexdigest(),
    }


def inspect_apk_hashes(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "size_human": format_bytes(path.stat().st_size),
        "md5": md5_file(path),
        "sha256": sha256_file(path),
        "dex_files": [],
    }

    with zipfile.ZipFile(path) as archive:
        dex_infos = [
            info
            for info in archive.infolist()
            if not info.is_dir()
            and re.fullmatch(r"classes(?:\d+)?\.dex", Path(info.filename).name)
            and "/" not in info.filename.strip("/")
        ]
        dex_infos.sort(key=lambda item: dex_sort_key(item.filename))
        result["dex_files"] = [hash_zip_entry(archive, info) for info in dex_infos]
        result["dex_count"] = len(dex_infos)
        result["dex_total_size_bytes"] = sum(info.file_size for info in dex_infos)
        result["dex_total_size_human"] = format_bytes(result["dex_total_size_bytes"])

    return result


def display_apk_hashes(title: str, data: dict[str, Any]) -> None:
    log(f"      {title}")
    log(f"      Tamaño APK: {data['size_human']} ({data['size_bytes']} bytes)")
    log(f"      MD5 APK:    {data['md5']}")
    log(f"      SHA-256:    {data['sha256']}")
    log(
        f"      DEX:        {data.get('dex_count', 0)} archivo(s), "
        f"{data.get('dex_total_size_human', '0 B')} sin comprimir"
    )

    dex_files = data.get("dex_files", [])
    if not dex_files:
        log("      Aviso: no se encontraron classes*.dex en la raíz del APK.")
        return

    for dex in dex_files:
        log(f"        - {dex['name']} ({dex['size_human']})")
        log(f"          MD5:    {dex['md5']}")
        log(f"          SHA256: {dex['sha256']}")
        log(f"          CRC32:  {dex['crc32']}")


def run_command(command: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(f'"{item}"' if " " in item else item for item in command)
    log(f"      $ {printable}")
    process = subprocess.Popen(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert process.stdout is not None
    for line in process.stdout:
        print(f"      {line}", end="")

    return_code = process.wait()
    if return_code != 0:
        raise PatchError(
            f"El comando terminó con código {return_code}: {printable}"
        )


def require_command(name: str) -> None:
    if shutil.which(name) is None:
        raise PatchError(
            f"No se encontró '{name}' en el PATH. "
            f"Instálalo antes de ejecutar el motor."
        )


def download_file(url: str, destination: Path) -> None:
    """
    Descarga una URL con sesión, cookies, redirecciones y validación básica.

    GNDEV_COOKIE puede contener una cabecera Cookie exportada por el usuario:
        export GNDEV_COOKIE='nombre=valor; otro=valor'

    Nota: una respuesta HTTP 403 causada por protección anti-bot del servidor
    no puede garantizarse que se resuelva únicamente cambiando cabeceras.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")

    if partial.exists():
        partial.unlink()

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PatchError(f"URL inválida: {url}")

    origin = f"{parsed.scheme}://{parsed.netloc}/"
    is_apkmirror = parsed.netloc.lower().endswith("apkmirror.com")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "application/vnd.android.package-archive,"
            "application/octet-stream;q=0.8,*/*;q=0.7"
        ),
        "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Referer": "https://www.apkmirror.com/" if is_apkmirror else origin,
        "Upgrade-Insecure-Requests": "1",
    }

    browser_cookie = os.environ.get("GNDEV_COOKIE", "").strip()
    if browser_cookie:
        headers["Cookie"] = browser_cookie

    cookie_jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookie_jar))

    if is_apkmirror:
        try:
            warmup = Request(
                "https://www.apkmirror.com/",
                headers={
                    "User-Agent": headers["User-Agent"],
                    "Accept-Language": headers["Accept-Language"],
                },
            )
            with opener.open(warmup, timeout=30) as response:
                response.read(1024)
        except (HTTPError, URLError, TimeoutError):
            pass

    request = Request(url, headers=headers, method="GET")

    try:
        with opener.open(request, timeout=120) as response, partial.open("wb") as out:
            status = getattr(response, "status", response.getcode())
            final_url = response.geturl()
            content_type = (
                response.headers.get_content_type()
                if hasattr(response.headers, "get_content_type")
                else response.headers.get("Content-Type", "")
            )
            total_header = response.headers.get("Content-Length")
            total = int(total_header) if total_header and total_header.isdigit() else 0

            if status != 200:
                raise PatchError(f"Descarga rechazada con HTTP {status}.")

            downloaded = 0
            last_percent = -1
            first_chunk = True

            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break

                if first_chunk:
                    first_chunk = False
                    sample = chunk[:512].lstrip().lower()
                    if (
                        sample.startswith(b"<!doctype html")
                        or sample.startswith(b"<html")
                        or b"<title>access denied" in sample
                        or b"<title>just a moment" in sample
                    ):
                        raise PatchError(
                            "El servidor devolvió una página HTML en vez de la APK. "
                            "Probablemente bloqueó la descarga automática."
                        )

                out.write(chunk)
                downloaded += len(chunk)

                if total:
                    percent = int(downloaded * 100 / total)
                    if percent >= last_percent + 10 or percent == 100:
                        log(
                            f"      Descarga: {percent}% "
                            f"({downloaded / 1024 / 1024:.1f} MB)"
                        )
                        last_percent = percent
                elif downloaded % (10 * 1024 * 1024) < len(chunk):
                    log(f"      Descargados: {downloaded / 1024 / 1024:.1f} MB")

            log(f"      URL final: {final_url}")
            log(f"      Content-Type: {content_type or 'desconocido'}")

    except HTTPError as exc:
        if partial.exists():
            partial.unlink()

        if exc.code == 403:
            raise PatchError(
                "HTTP 403: el servidor rechazó la sesión automatizada. "
                "En APKMirror suele requerirse descargar desde el navegador "
                "o usar una URL directa autorizada al archivo."
            ) from exc

        raise PatchError(
            f"El servidor respondió HTTP {exc.code}. "
            "La URL puede haber vencido o estar protegida."
        ) from exc

    except (URLError, TimeoutError) as exc:
        if partial.exists():
            partial.unlink()
        reason = getattr(exc, "reason", str(exc))
        raise PatchError(f"No se pudo descargar la APK: {reason}") from exc

    except Exception:
        if partial.exists():
            partial.unlink()
        raise

    if not partial.exists() or partial.stat().st_size == 0:
        if partial.exists():
            partial.unlink()
        raise PatchError("La descarga terminó, pero el archivo está vacío.")

    if not zipfile.is_zipfile(partial):
        partial.unlink(missing_ok=True)
        raise PatchError(
            "El archivo descargado no es una APK/ZIP válida. "
            "Puede ser HTML, un bloqueo o un enlace incorrecto."
        )

    with zipfile.ZipFile(partial) as archive:
        if "AndroidManifest.xml" not in archive.namelist():
            partial.unlink(missing_ok=True)
            raise PatchError(
                "El ZIP descargado no contiene AndroidManifest.xml; "
                "no parece una APK válida."
            )

    partial.replace(destination)
    log(f"      APK guardada: {destination}")


def download_official_whatsapp_apk(
    url: str,
    destination: Path,
) -> None:
    """
    Descarga el APK oficial con el mismo curl que funcionó manualmente.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")

    if partial.exists():
        partial.unlink()

    log("      Descargando APK oficial con curl...")

    command = [
        "curl",
        "-fL",
        "--retry", "3",
        "-A", "Mozilla/5.0",
        "-e", WHATSAPP_ANDROID_PAGE,
        url,
        "-o", str(partial),
    ]

    run_command(command)

    if not partial.exists() or partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        raise PatchError(
            "La descarga terminó, pero el archivo está vacío."
        )

    if not zipfile.is_zipfile(partial):
        partial.unlink(missing_ok=True)
        raise PatchError(
            "El archivo descargado no es una APK/ZIP válida."
        )

    with zipfile.ZipFile(partial) as archive:
        if "AndroidManifest.xml" not in archive.namelist():
            partial.unlink(missing_ok=True)
            raise PatchError(
                "La descarga no contiene AndroidManifest.xml."
            )

    partial.replace(destination)
    log(f"      Descarga terminada: {destination}")

def validate_apk(path: Path) -> None:
    if not path.is_file():
        raise PatchError(f"No existe la APK: {path}")
    if not zipfile.is_zipfile(path):
        raise PatchError(
            f"El archivo no parece ser una APK/ZIP válida: {path}. "
            "Puede haberse descargado una página HTML."
        )
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "AndroidManifest.xml" not in names:
            raise PatchError("El archivo ZIP no contiene AndroidManifest.xml.")


def safe_destination(root: Path, member_name: str) -> Path:
    normalized = PurePosixPath(member_name)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise PatchError(f"Ruta insegura dentro del ZIP: {member_name}")

    destination = (root / Path(*normalized.parts)).resolve()
    root_resolved = root.resolve()

    try:
        destination.relative_to(root_resolved)
    except ValueError as exc:
        raise PatchError(f"Ruta fuera del destino permitido: {member_name}") from exc

    return destination


def safe_extract_zip(
    zip_path: Path,
    destination: Path,
    overwrite: bool = True,
) -> tuple[int, int]:
    destination.mkdir(parents=True, exist_ok=True)
    created = 0
    skipped = 0

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            output = safe_destination(destination, member.filename)

            if member.is_dir():
                output.mkdir(parents=True, exist_ok=True)
                continue

            if output.exists() and not overwrite:
                skipped += 1
                continue

            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, output.open("wb") as target:
                shutil.copyfileobj(source, target)
            created += 1

    return created, skipped


def parse_fields(block_lines: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key: str | None = None
    current_value: list[str] = []

    def save_current() -> None:
        nonlocal current_key, current_value
        if current_key is not None:
            fields[current_key] = "\n".join(current_value).strip()
        current_key = None
        current_value = []

    field_pattern = re.compile(r"^([A-Z][A-Z0-9_]*)\s*:\s*(.*)$")

    for raw_line in block_lines:
        line = raw_line.rstrip("\r\n")
        match = field_pattern.match(line.strip())

        if match:
            save_current()
            current_key = match.group(1)
            inline_value = match.group(2)
            current_value = [inline_value] if inline_value else []
        elif current_key is not None:
            current_value.append(line)

    save_current()
    return fields


def parse_manifest(text: str) -> tuple[dict[str, str], list[dict[str, Any]]]:
    lines = text.splitlines()
    metadata: dict[str, str] = {}
    operations: list[dict[str, Any]] = []
    index = 0
    header_pattern = re.compile(r"^\[(/?)([A-Z][A-Z0-9_]*)\]$")

    while index < len(lines):
        stripped = lines[index].strip()
        match = header_pattern.match(stripped)

        if not match:
            index += 1
            continue

        closing, tag = match.groups()
        if closing:
            index += 1
            continue

        if tag in OPERATION_TAGS:
            closing_tag = f"[/{tag}]"
            block: list[str] = []
            index += 1

            while index < len(lines) and lines[index].strip() != closing_tag:
                block.append(lines[index])
                index += 1

            if index >= len(lines):
                raise PatchError(f"Falta cerrar el bloque [{tag}] con {closing_tag}")

            operation = parse_fields(block)
            operation["TYPE"] = tag
            operations.append(operation)
            index += 1
            continue

        value_lines: list[str] = []
        index += 1

        while index < len(lines):
            next_line = lines[index].strip()
            if header_pattern.match(next_line):
                break
            value_lines.append(lines[index])
            index += 1

        metadata[tag] = "\n".join(value_lines).strip()

    return metadata, operations


def read_patch_manifest_from_zip(
    patch_zip: Path,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """
    Lee patch.txt directamente desde el ZIP para obtener metadatos
    antes de mostrar el banner.
    """
    with zipfile.ZipFile(patch_zip) as archive:
        names = [
            name
            for name in archive.namelist()
            if PurePosixPath(name).name.lower() == "patch.txt"
        ]

        if not names:
            raise PatchError("El ZIP del parche no contiene patch.txt.")

        if len(names) > 1:
            raise PatchError(
                "El ZIP contiene más de un patch.txt; deja solo uno."
            )

        raw = archive.read(names[0])

    try:
        manifest_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PatchError(
            "patch.txt debe estar codificado en UTF-8."
        ) from exc

    return parse_manifest(manifest_text)


def find_manifest(patch_root: Path) -> Path:
    direct = patch_root / "patch.txt"
    if direct.is_file():
        return direct

    candidates = list(patch_root.rglob("patch.txt"))
    if not candidates:
        raise PatchError("El ZIP del parche no contiene patch.txt.")
    if len(candidates) > 1:
        raise PatchError("El ZIP contiene más de un patch.txt; deja solo uno.")
    return candidates[0]


def bool_value(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


def detect_package_name(project_dir: Path) -> str | None:
    manifest = project_dir / "AndroidManifest.xml"
    if not manifest.is_file():
        return None

    text = manifest.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'\bpackage\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else None


def validate_package(package_rule: str, detected: str | None) -> None:
    if not package_rule or package_rule.strip() == "*":
        return

    if not detected:
        raise PatchError(
            "El parche restringe el paquete, pero no se pudo detectar "
            "el packageName de la APK."
        )

    allowed = [
        item.strip()
        for item in re.split(r"[\n,;]+", package_rule)
        if item.strip()
    ]

    if not any(fnmatch.fnmatchcase(detected, rule) for rule in allowed):
        raise PatchError(
            f"Paquete incompatible. Detectado: {detected}. "
            f"Permitidos: {', '.join(allowed)}"
        )


def resolve_project_target(project_dir: Path, target_value: str) -> Path:
    target = target_value.strip() if target_value else "/"

    if target in {"/", ".", "./"}:
        return project_dir

    if target.upper() == "AUTO_SMALI":
        default_smali = project_dir / "smali"
        default_smali.mkdir(parents=True, exist_ok=True)
        return default_smali

    relative = PurePosixPath(target.lstrip("/"))
    if ".." in relative.parts:
        raise PatchError(f"TARGET inseguro: {target}")

    result = (project_dir / Path(*relative.parts)).resolve()
    try:
        result.relative_to(project_dir.resolve())
    except ValueError as exc:
        raise PatchError(f"TARGET fuera del proyecto: {target}") from exc

    return result


def apply_add_files(
    operation: dict[str, Any],
    patch_root: Path,
    project_dir: Path,
) -> dict[str, Any]:
    source_value = operation.get("SOURCE", "").strip()
    if not source_value:
        raise PatchError("[ADD_FILES] necesita SOURCE.")

    source = (patch_root / source_value).resolve()
    try:
        source.relative_to(patch_root.resolve())
    except ValueError as exc:
        raise PatchError(f"SOURCE fuera del parche: {source_value}") from exc

    if not source.exists():
        raise PatchError(f"No existe SOURCE dentro del parche: {source_value}")

    target = resolve_project_target(project_dir, operation.get("TARGET", "/"))
    extract = bool_value(operation.get("EXTRACT"), default=False)
    overwrite = bool_value(operation.get("OVERWRITE"), default=True)

    if extract:
        if not source.is_file() or not zipfile.is_zipfile(source):
            raise PatchError(
                f"EXTRACT:true requiere que SOURCE sea un ZIP válido: {source_value}"
            )
        created, skipped = safe_extract_zip(source, target, overwrite=overwrite)
        return {
            "type": "ADD_FILES",
            "source": source_value,
            "target": str(target),
            "created": created,
            "skipped": skipped,
        }

    copied = 0
    skipped = 0

    if source.is_dir():
        for item in source.rglob("*"):
            if item.is_dir():
                continue
            relative = item.relative_to(source)
            output = target / relative
            if output.exists() and not overwrite:
                skipped += 1
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, output)
            copied += 1
    else:
        target.mkdir(parents=True, exist_ok=True)
        output = target / source.name
        if output.exists() and not overwrite:
            skipped += 1
        else:
            shutil.copy2(source, output)
            copied += 1

    return {
        "type": "ADD_FILES",
        "source": source_value,
        "target": str(target),
        "created": copied,
        "skipped": skipped,
    }


def find_target_files(project_dir: Path, target_pattern: str) -> list[Path]:
    """
    Resuelve TARGET de forma recursiva y compatible con APK multidex.

    Comportamiento:
    - "*.smali" busca recursivamente dentro de smali/ y smali_classesN/.
    - "LX/*.smali" se interpreta dentro de todas las carpetas Smali.
    - "smali*/**/*.smali" respeta explícitamente todas las DEX.
    - Los patrones de recursos, por ejemplo res/**/*.xml, se mantienen iguales.
    """
    normalized = target_pattern.strip().replace("\\", "/").lstrip("./")

    if not normalized:
        return []

    smali_roots = sorted(
        path
        for path in project_dir.iterdir()
        if path.is_dir()
        and (
            path.name == "smali"
            or re.fullmatch(r"smali_classes\d+", path.name)
        )
    )

    results: list[Path] = []

    # TARGET: smali*/...
    # Busca el sufijo indicado dentro de cada carpeta DEX.
    if normalized.startswith("smali*/"):
        suffix = normalized[len("smali*/"):]

        for smali_root in smali_roots:
            results.extend(
                path
                for path in smali_root.glob(suffix)
                if path.is_file()
            )

        return sorted(set(results))

    # TARGET: *.smali
    # El patrón antiguo ahora busca recursivamente en todas las DEX.
    if normalized == "*.smali":
        for smali_root in smali_roots:
            results.extend(
                path
                for path in smali_root.rglob("*.smali")
                if path.is_file()
            )

        return sorted(set(results))

    # TARGET relativo a una DEX, por ejemplo:
    # LX/*.smali
    # com/empresa/**/*.smali
    if normalized.endswith(".smali") and not normalized.startswith(
        ("smali/", "smali_classes", "**/")
    ):
        search_pattern = (
            normalized.replace("*.smali", "**/*.smali")
            if "/" not in normalized and "**/" not in normalized
            else normalized
        )

        for smali_root in smali_roots:
            results.extend(
                path
                for path in smali_root.glob(search_pattern)
                if path.is_file()
            )

        return sorted(set(results))

    # Otros patrones, como res/**/*.xml o **/*.smali.
    return sorted(
        path
        for path in project_dir.glob(normalized)
        if path.is_file()
    )

def apply_match_replace(
    operation: dict[str, Any],
    project_dir: Path,
) -> dict[str, Any]:
    target_pattern = operation.get("TARGET", "").strip()
    match_value = operation.get("MATCH", "")
    replacement = operation.get("REPLACE", "")
    use_regex = bool_value(operation.get("REGEX"), default=False)
    required = bool_value(operation.get("REQUIRED"), default=False)
    use_dotall = bool_value(operation.get("DOTALL"), default=False)
    ignore_case = bool_value(operation.get("IGNORE_CASE"), default=False)

    if not target_pattern:
        raise PatchError("[MATCH_REPLACE] necesita TARGET.")
    if match_value == "":
        raise PatchError("[MATCH_REPLACE] necesita MATCH.")

    files = find_target_files(project_dir, target_pattern)

    log(f"          TARGET: {target_pattern}")
    log(f"          Archivos encontrados: {len(files)}")

    if files:
        preview_limit = 3
        for preview in files[:preview_limit]:
            try:
                relative = preview.relative_to(project_dir)
            except ValueError:
                relative = preview
            log(f"            · {relative}")

        if len(files) > preview_limit:
            log(f"            · ... y {len(files) - preview_limit} más")

    changed_files = 0
    total_matches = 0
    skipped_binary = 0

    compiled: re.Pattern[str] | None = None
    regex_flags = re.MULTILINE

    if use_dotall:
        regex_flags |= re.DOTALL
    if ignore_case:
        regex_flags |= re.IGNORECASE

    if use_regex:
        try:
            compiled = re.compile(match_value, flags=regex_flags)
        except re.error as exc:
            raise PatchError(f"Regex inválida: {exc}") from exc

        log(
            "          Regex activa: true"
            f" | MULTILINE:true"
            f" | DOTALL:{str(use_dotall).lower()}"
            f" | IGNORE_CASE:{str(ignore_case).lower()}"
        )
    else:
        log("          Regex activa: false")

    for path in files:
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            skipped_binary += 1
            continue

        if use_regex:
            assert compiled is not None
            modified, count = compiled.subn(replacement, original)
        else:
            count = original.count(match_value)
            modified = original.replace(match_value, replacement)

        if count:
            path.write_text(modified, encoding="utf-8")
            changed_files += 1
            total_matches += count

    if required and total_matches == 0:
        raise PatchError(
            "La operación REQUIRED no encontró coincidencias. "
            f"TARGET={target_pattern}, archivos={len(files)}"
        )

    min_matches = operation.get("MIN_MATCHES", "").strip()
    max_matches = operation.get("MAX_MATCHES", "").strip()

    if min_matches:
        try:
            minimum = int(min_matches)
        except ValueError as exc:
            raise PatchError("MIN_MATCHES debe ser un entero.") from exc

        if total_matches < minimum:
            raise PatchError(
                f"Coincidencias insuficientes: {total_matches}; mínimo: {minimum}"
            )

    if max_matches:
        try:
            maximum = int(max_matches)
        except ValueError as exc:
            raise PatchError("MAX_MATCHES debe ser un entero.") from exc

        if total_matches > maximum:
            raise PatchError(
                f"Demasiadas coincidencias: {total_matches}; máximo: {maximum}"
            )

    return {
        "type": "MATCH_REPLACE",
        "target": target_pattern,
        "files_scanned": len(files),
        "changed_files": changed_files,
        "matches": total_matches,
        "skipped_binary": skipped_binary,
        "regex": use_regex,
        "dotall": use_dotall,
        "ignore_case": ignore_case,
    }


def remove_all_line_directives(project_dir: Path) -> dict[str, int]:
    pattern = re.compile(r"^[ \t]*\.line(?:[ \t].*|[ \t]*)$", flags=re.MULTILINE)
    files_scanned = 0
    changed_files = 0
    removed = 0

    for smali in project_dir.rglob("*.smali"):
        files_scanned += 1
        try:
            original = smali.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        modified, count = pattern.subn("", original)
        if count:
            # Evita acumular demasiadas líneas vacías.
            modified = re.sub(r"\n{4,}", "\n\n\n", modified)
            smali.write_text(modified, encoding="utf-8")
            changed_files += 1
            removed += count

    return {
        "files_scanned": files_scanned,
        "changed_files": changed_files,
        "removed": removed,
    }


def display_patch_info(metadata: dict[str, str]) -> None:
    log("=" * 62)
    log("                    GNDEV PATCH ENGINE")
    log("=" * 62)
    log(f"Parche:      {metadata.get('PATCH_NAME', 'Sin nombre')}")
    log(f"Versión:     {metadata.get('PATCH_VERSION', 'Sin versión')}")
    log(f"Autor:       {metadata.get('AUTHOR', 'No especificado')}")
    log(f"Paquete:     {metadata.get('PACKAGE', '*')}")
    description = metadata.get("DESCRIPTION", "")
    if description:
        log("\nDescripción:")
        for line in description.splitlines():
            log(f"  {line}")
    log("=" * 62)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Descarga/descompila una APK, aplica un parche ZIP, "
            "elimina .line y recompila."
        )
    )

    apk_group = parser.add_mutually_exclusive_group(required=False)
    apk_group.add_argument("--apk-url", help="URL directa del archivo APK.")
    apk_group.add_argument("--apk", type=Path, help="Ruta de una APK local.")
    apk_group.add_argument(
        "--official-whatsapp",
        action="store_true",
        help=(
            "Obtiene automáticamente el enlace vigente del APK desde "
            "la página oficial de WhatsApp. También es el modo predeterminado."
        ),
    )

    parser.add_argument(
        "--patch",
        type=Path,
        default=Path("GenOsPatch.zip"),
        help=(
            "ZIP del parche. Por defecto usa ./GenOsPatch.zip."
        ),
    )
    parser.add_argument(
        "--keep-decoded",
        action="store_true",
        help=(
            "Compatibilidad: esta opción se ignora; la carpeta descompilada "
            "se elimina obligatoriamente tras compilar."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("WhatsApp-patched-unsigned.apk"),
        help=(
            "APK recompilado. Por defecto: ./WhatsApp-patched-unsigned.apk"
        ),
    )
    parser.add_argument(
        "--workdir",
        type=Path,
        default=Path("build"),
        help="Carpeta de trabajo. Por defecto: ./build",
    )
    parser.add_argument(
        "--keep-lines",
        action="store_true",
        help="No elimina las directivas .line.",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="No borra la carpeta temporal al terminar.",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Aplica el parche, pero no recompila.",
    )

    args = parser.parse_args()

    require_command("java")
    require_command("apktool")
    require_command("curl")

    patch_zip = args.patch.expanduser().resolve()
    if not patch_zip.is_file() or not zipfile.is_zipfile(patch_zip):
        raise PatchError(f"El parche no es un ZIP válido: {patch_zip}")

    banner_metadata, _ = read_patch_manifest_from_zip(patch_zip)
    script_author = (
        banner_metadata.get("SCRIPT_AUTHOR")
        or banner_metadata.get("AUTHOR")
        or "GenOs"
    )
    youtube_channel = (
        banner_metadata.get("YOUTUBE_CHANNEL")
        or banner_metadata.get("YOUTUBE")
        or "No configurado en patch.txt"
    )

    display_engine_banner(
        script_author=script_author,
        youtube_channel=youtube_channel,
    )

    temporary_context: tempfile.TemporaryDirectory[str] | None = None

    workdir = args.workdir.expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    input_dir = workdir / "input"
    patch_root = workdir / "patch"
    project_dir = workdir / "decoded"
    report_path = workdir / "patch-report.json"

    input_dir.mkdir(parents=True, exist_ok=True)

    if patch_root.exists():
        shutil.rmtree(patch_root)
    patch_root.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "engine_version": ENGINE_VERSION,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "operations": [],
        "workdir": str(workdir),
    }

    try:
        log("\n[1/7] Preparando APK...")
        if args.apk_url:
            apk_path = input_dir / "downloaded.apk"
            report["apk_source"] = "custom_url"
            report["source_url"] = args.apk_url
            log("      Fuente: URL proporcionada")
            log(f"      URL: {args.apk_url}")
            download_file(args.apk_url, apk_path)

        elif args.apk:
            source_apk = args.apk.expanduser().resolve()
            if not source_apk.is_file():
                raise PatchError(f"No existe la APK local: {source_apk}")
            apk_path = input_dir / source_apk.name
            report["apk_source"] = "local_file"
            report["source_file"] = str(source_apk)
            log(f"      Fuente: APK local ({source_apk})")
            shutil.copy2(source_apk, apk_path)

        else:
            report["apk_source"] = "official_whatsapp"
            log("      Fuente: página oficial de WhatsApp")
            log("      Buscando el enlace directo vigente...")
            official_url = resolve_official_whatsapp_apk_url()
            report["source_url"] = official_url
            log(f"      URL oficial encontrada: {official_url}")
            apk_path = (Path.cwd() / "WhatsApp.apk").resolve()
            log(f"      Descargando APK oficial en: {apk_path}")
            download_official_whatsapp_apk(official_url, apk_path)

        validate_apk(apk_path)
        input_hashes = inspect_apk_hashes(apk_path)
        report["input_apk"] = str(apk_path)
        report["input_md5"] = input_hashes["md5"]
        report["input_sha256"] = input_hashes["sha256"]
        report["input_integrity"] = input_hashes
        log(f"      APK válida: {apk_path.name}")
        display_apk_hashes("Integridad original (antes de descompilar):", input_hashes)

        log("\n[2/7] Abriendo paquete de parche...")
        safe_extract_zip(patch_zip, patch_root, overwrite=True)
        manifest_path = find_manifest(patch_root)
        manifest_text = manifest_path.read_text(encoding="utf-8-sig")
        metadata, operations = parse_manifest(manifest_text)

        min_engine = metadata.get("MIN_ENGINE_VER", "1").strip()
        try:
            required_engine = int(min_engine)
        except ValueError as exc:
            raise PatchError("[MIN_ENGINE_VER] debe ser un número entero.") from exc

        if required_engine > ENGINE_VERSION:
            raise PatchError(
                f"El parche necesita motor {required_engine}, "
                f"pero este archivo usa motor {ENGINE_VERSION}."
            )

        display_patch_info(metadata)
        report["metadata"] = metadata
        report["script_author"] = (
            metadata.get("SCRIPT_AUTHOR")
            or metadata.get("AUTHOR")
            or "GenOs"
        )
        report["youtube_channel"] = (
            metadata.get("YOUTUBE_CHANNEL")
            or metadata.get("YOUTUBE")
            or ""
        )

        log("\n[3/7] Descompilando APK con Apktool...")
        if project_dir.exists():
            shutil.rmtree(project_dir)
        run_command(
            ["apktool", "d", "-f", str(apk_path), "-o", str(project_dir)]
        )

        detected_package = detect_package_name(project_dir)
        report["detected_package"] = detected_package
        validate_package(metadata.get("PACKAGE", "*"), detected_package)
        log(f"      Paquete detectado: {detected_package or 'desconocido'}")

        log("\n[4/7] Eliminando directivas .line antes del parche...")
        if args.keep_lines:
            log("      Omitido por --keep-lines.")
            report["remove_lines"] = {"skipped": True}
        else:
            line_result = remove_all_line_directives(project_dir)
            report["remove_lines"] = line_result
            log(
                f"      .line eliminados: {line_result['removed']} | "
                f"Archivos modificados: {line_result['changed_files']} | "
                f"Smali revisados: {line_result['files_scanned']}"
            )

        log("\n[5/7] Aplicando operaciones del parche...")
        if not operations:
            log("      El manifiesto no contiene operaciones.")

        for number, operation in enumerate(operations, start=1):
            operation_type = operation["TYPE"]
            name = operation.get("NAME", operation_type)
            log(f"      [{number}/{len(operations)}] {name}")

            if operation_type == "ADD_FILES":
                result = apply_add_files(operation, patch_root, project_dir)
                log(
                    f"          Agregados: {result['created']} | "
                    f"Omitidos: {result['skipped']}"
                )
            elif operation_type == "MATCH_REPLACE":
                result = apply_match_replace(operation, project_dir)
                log(
                    f"          Coincidencias: {result['matches']} | "
                    f"Archivos modificados: {result['changed_files']}"
                )
            else:
                raise PatchError(f"Operación no soportada: {operation_type}")

            result["name"] = name
            report["operations"].append(result)

        log("\n[6/7] Guardando reporte previo...")
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log(f"      Reporte: {report_path}")

        if args.no_build:
            log("\n[7/7] Compilación omitida por --no-build.")
            log(f"Proyecto parchado: {project_dir}")
            return 0

        log("\n[7/7] Recompilando APK...")
        output_apk = args.output.expanduser().resolve()

        output_apk.parent.mkdir(parents=True, exist_ok=True)
        if output_apk.exists():
            output_apk.unlink()

        run_command(
            ["apktool", "b", str(project_dir), "-o", str(output_apk)]
        )
        
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)

        if project_dir.exists():
            raise PatchError(
                f"No se pudo eliminar la carpeta descompilada: {project_dir}"
            )

        report["decoded_removed"] = True
        report["decoded_path"] = str(project_dir)
        log(f"      Proyecto descompilado eliminado: {project_dir}")
        
        validate_apk(output_apk)
        output_hashes = inspect_apk_hashes(output_apk)
        report["output_apk"] = str(output_apk)
        report["output_md5"] = output_hashes["md5"]
        report["output_sha256"] = output_hashes["sha256"]
        report["output_integrity"] = output_hashes
        report["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        log("\n" + "=" * 62)
        log("PARCHE APLICADO Y APK RECOMPILADA")
        log(f"Salida: {output_apk}")
        display_apk_hashes("Integridad recompilada:", output_hashes)
        log(f"Reporte: {report_path}")
        log(f"Carpeta descompilada eliminada: {project_dir}")
        log("Nota: el APK recompilado está sin firmar.")
        log("MD5 se muestra solo para identificación; usa SHA-256 para integridad.")
        log("=" * 62)

        if args.keep_workdir or args.workdir:
            log(f"Carpeta de trabajo: {workdir}")

        return 0

    finally:
        if temporary_context is not None:
            if args.keep_workdir:
                # TemporaryDirectory borraría la carpeta al salir. La copiamos.
                preserved = Path.cwd() / f"gndev-workdir-{int(time.time())}"
                shutil.copytree(workdir, preserved)
                log(f"Carpeta temporal conservada en: {preserved}")
            temporary_context.cleanup()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PatchError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nProceso cancelado por el usuario.", file=sys.stderr)
        raise SystemExit(130)
