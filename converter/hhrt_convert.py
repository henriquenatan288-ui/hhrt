#!/usr/bin/env python3
"""Convert resource-only Fabric JAR payloads into a documented Horizon .hmod layout.

This tool never loads or executes Java bytecode. Its output still needs validation with
the exact Horizon build that will consume it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scanner.hhrt_scanner import ScanError, scan_jar  # noqa: E402

MAX_FILES = 65_536
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
VALID_ID = re.compile(r"^[a-z0-9_]{1,64}$")
VALID_NAMESPACE = re.compile(r"^[a-z0-9_]{1,64}$")
VALID_RESOURCE_PART = re.compile(r"^[a-z0-9_.-]+$")


class ConvertError(Exception):
    """Raised when a JAR cannot be safely represented as a Horizon content mod."""


def _toml_string(value: str) -> str:
    # JSON basic-string escaping is compatible with TOML basic strings for these values.
    return json.dumps(value, ensure_ascii=False)


def _metadata_from_jar(jar: zipfile.ZipFile) -> dict[str, Any]:
    try:
        raw = jar.read("fabric.mod.json")
        metadata = json.loads(raw.decode("utf-8-sig"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        raise ConvertError(f"Não foi possível ler fabric.mod.json: {exc}") from exc
    if not isinstance(metadata, dict):
        raise ConvertError("fabric.mod.json precisa conter um objeto JSON.")
    return metadata


def _get_mod_id(metadata: dict[str, Any], override: str | None) -> str:
    mod_id = override or metadata.get("id")
    if not isinstance(mod_id, str) or not VALID_ID.fullmatch(mod_id):
        raise ConvertError(
            "O ID precisa usar 1–64 caracteres a-z, 0-9 ou _. "
            "Use --id para informar um ID Horizon válido."
        )
    return mod_id


def _get_authors(metadata: dict[str, Any]) -> list[str]:
    authors = metadata.get("authors", [])
    if isinstance(authors, str):
        authors = [authors]
    if not isinstance(authors, list):
        return []
    return [item for item in authors if isinstance(item, str) and item.strip()][:32]


def _check_dependencies(metadata: dict[str, Any]) -> None:
    dependencies = metadata.get("depends", {})
    if not isinstance(dependencies, dict):
        return
    core = {"minecraft", "fabricloader", "java"}
    unresolved = sorted(
        key for key in dependencies
        if isinstance(key, str) and key not in core
    )
    if unresolved:
        raise ConvertError(
            "O mod exige outras dependências Fabric que não são traduzidas para Horizon: "
            + ", ".join(unresolved)
        )


def _resource_path_info(name: str) -> tuple[str, str, str]:
    path = PurePosixPath(name)
    parts = path.parts
    if len(parts) < 3 or parts[0] not in {"assets", "data"}:
        raise ConvertError(f"Caminho de recurso inválido: {name}")
    root, namespace = parts[0], parts[1]
    relative = "/".join(parts[2:])
    if not VALID_NAMESPACE.fullmatch(namespace) or not relative:
        raise ConvertError(f"Namespace ou caminho inválido: {name}")
    if "//" in name or any(part in {".", ".."} for part in name.split("/")):
        raise ConvertError(f"Caminho não canônico: {name}")
    if any(not VALID_RESOURCE_PART.fullmatch(part) for part in parts[2:]):
        raise ConvertError(f"O caminho contém caracteres fora do padrão de recursos: {name}")

    if namespace == "horizon":
        raise ConvertError("O namespace 'horizon' é reservado e não pode ser importado.")
    if namespace == "minecraft":
        if root != "data" or not relative.startswith("tags/"):
            raise ConvertError(
                "No Horizon, arquivos sob 'minecraft' só podem ser tags em data/minecraft/tags/."
            )
    if namespace == "c":
        if root != "data" or not relative.startswith("tags/"):
            raise ConvertError(
                "O namespace de convenção 'c' só pode conter tags em data/c/tags/."
            )
    return root, namespace, relative


def _manifest(
    metadata: dict[str, Any],
    mod_id: str,
    side: str,
    extra_namespaces: list[str],
) -> str:
    name = metadata.get("name")
    if not isinstance(name, str) or not name.strip():
        name = mod_id
    version = metadata.get("version")
    if not isinstance(version, str) or not version.strip():
        version = "0.0.0-import"
    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        description = f"Resource/data import from Fabric mod {mod_id}; Java code is not included."
    authors = _get_authors(metadata) or ["Unknown"]
    lines = [
        f"id = {_toml_string(mod_id)}",
        f"name = {_toml_string(name)}",
        f"version = {_toml_string(version)}",
        f"description = {_toml_string(description)}",
        "authors = [" + ", ".join(_toml_string(author) for author in authors) + "]",
        'api = "0.2"',
        f"side = {_toml_string(side)}",
        'capabilities = ["registries"]',
    ]
    if extra_namespaces:
        lines.append(
            "namespaces = [" + ", ".join(_toml_string(ns) for ns in extra_namespaces) + "]"
        )
    return "\n".join(lines) + "\n"


def convert_jar(
    jar_path: str | Path,
    output_path: str | Path,
    side: str = "both",
    id_override: str | None = None,
) -> dict[str, Any]:
    if side not in {"client", "server", "both"}:
        raise ConvertError("side deve ser client, server ou both.")

    scan = scan_jar(str(jar_path))
    assessment = scan["assessment"]["classification"]
    if assessment != "resource_candidate":
        raise ConvertError(
            f"Conversão recusada: o Scanner classificou o mod como '{assessment}'. "
            "Este conversor só aceita JARs sem bytecode, entrypoints, Mixins ou bibliotecas."
        )

    out = Path(output_path)
    if out.suffix.lower() != ".hmod":
        raise ConvertError("O arquivo de saída precisa terminar em .hmod.")
    if out.exists():
        raise ConvertError(f"O arquivo de saída já existe: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)

    selected: list[tuple[zipfile.ZipInfo, str]] = []
    namespaces: set[str] = set()
    total_bytes = 0

    try:
        with zipfile.ZipFile(jar_path, "r") as source:
            metadata = _metadata_from_jar(source)
            mod_id = _get_mod_id(metadata, id_override)
            _check_dependencies(metadata)

            infos = source.infolist()
            file_names = [info.filename for info in infos if not info.is_dir()]
            if len(file_names) != len(set(file_names)):
                raise ConvertError("O JAR contém caminhos duplicados; conversão recusada.")
            if len(file_names) > MAX_FILES:
                raise ConvertError(f"O JAR excede o limite de {MAX_FILES} arquivos.")

            for info in infos:
                if info.is_dir():
                    continue
                name = info.filename
                if name.startswith("assets/") or name.startswith("data/"):
                    if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
                        raise ConvertError(f"Caminho inseguro no JAR: {name}")
                    unix_mode = info.external_attr >> 16
                    if stat.S_ISLNK(unix_mode):
                        raise ConvertError(f"Links simbólicos não são aceitos: {name}")
                    if info.file_size > MAX_FILE_BYTES:
                        raise ConvertError(
                            f"{name} excede o limite de {MAX_FILE_BYTES // (1024 * 1024)} MiB."
                        )
                    total_bytes += info.file_size
                    if total_bytes > MAX_TOTAL_BYTES:
                        raise ConvertError(
                            f"Os recursos excedem o limite total de "
                            f"{MAX_TOTAL_BYTES // (1024 * 1024)} MiB."
                        )
                    _, namespace, _ = _resource_path_info(name)
                    if namespace not in {mod_id, "minecraft", "c"}:
                        namespaces.add(namespace)
                    selected.append((info, name))

            if not selected:
                raise ConvertError("O JAR não contém arquivos assets/ ou data/ conversíveis.")

            manifest = _manifest(metadata, mod_id, side, sorted(namespaces))
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{out.name}.", suffix=".tmp", dir=str(out.parent)
            )
            os.close(fd)
            temp_path = Path(temp_name)
            try:
                with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as target:
                    target.writestr("horizon-mod.toml", manifest)
                    for info, name in selected:
                        # Reading through zipfile verifies decompression/CRC before writing.
                        target.writestr(name, source.read(info))
                os.replace(temp_path, out)
            finally:
                if temp_path.exists():
                    temp_path.unlink()
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ConvertError(f"Falha ao ler ou gravar o pacote: {exc}") from exc

    return {
        "output": str(out),
        "mod_id": mod_id,
        "files_copied": len(selected),
        "uncompressed_bytes": total_bytes,
        "namespaces": sorted(namespaces),
        "side": side,
        "horizon_content_api": "0.2",
        "warnings": [
            "O conversor preserva assets/data; não traduz lógica nem formatos específicos de mods.",
            "O pacote usa a documentação atual do Horizon Content API 0.2; não foi validado no APK 0.7.7.",
            "A documentação atual consultada descreve Minecraft 26.3; suporte a 26.2 ainda precisa de validação.",
            "Execute cargo horizon-mod check no ambiente Horizon correspondente antes de instalar.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Empacota apenas assets/data de um JAR Fabric sem código Java em .hmod."
    )
    parser.add_argument("jar", help="Arquivo Fabric .jar")
    parser.add_argument("-o", "--output", required=True, help="Arquivo de saída .hmod")
    parser.add_argument("--side", choices=("client", "server", "both"), default="both")
    parser.add_argument("--id", dest="id_override", help="ID Horizon válido (opcional)")
    args = parser.parse_args()

    try:
        result = convert_jar(args.jar, args.output, args.side, args.id_override)
    except (ScanError, ConvertError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
