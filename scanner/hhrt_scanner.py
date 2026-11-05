#!/usr/bin/env python3
"""Static Fabric JAR scanner for HHRT. Does not load or execute Java code."""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import PurePosixPath
from typing import Any

MAX_ENTRIES = 100_000
MAX_METADATA_BYTES = 2 * 1024 * 1024
RESOURCE_PREFIXES = (
    "assets/", "data/", "pack.mcmeta", "fabric.mod.json",
    "LICENSE", "LICENSE.txt", "META-INF/"
)
CODE_SUFFIXES = (".class", ".jar", ".so", ".dll", ".dylib")


class ScanError(Exception):
    pass


def _safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and "\\" not in name


def _read_json(zf: zipfile.ZipFile, name: str) -> Any:
    info = zf.getinfo(name)
    if info.file_size > MAX_METADATA_BYTES:
        raise ScanError(f"{name} excede o limite de {MAX_METADATA_BYTES} bytes")
    return json.loads(zf.read(name).decode("utf-8-sig"))


def _as_mod_list(metadata: Any) -> list[dict[str, Any]]:
    if isinstance(metadata, dict):
        return [metadata]
    if isinstance(metadata, list):
        return [item for item in metadata if isinstance(item, dict)]
    return []


def scan_jar(path: str) -> dict[str, Any]:
    try:
        zf = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise ScanError(f"Não foi possível abrir o JAR: {exc}") from exc

    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ScanError(f"JAR contém entradas demais ({len(infos)}); limite: {MAX_ENTRIES}")
        names = [i.filename for i in infos if not i.is_dir()]
        unsafe = [name for name in names if not _safe_name(name)]
        safe_names = [name for name in names if _safe_name(name)]
        if "fabric.mod.json" not in safe_names:
            raise ScanError("fabric.mod.json não encontrado; arquivo não identificado como mod Fabric")

        metadata = _read_json(zf, "fabric.mod.json")
        mods = _as_mod_list(metadata)
        if not mods:
            raise ScanError("fabric.mod.json não contém um objeto de mod válido")

        all_classes = [n for n in safe_names if n.endswith(".class")]
        mixin_configs: set[str] = set()
        entrypoints: list[dict[str, Any]] = []
        dependencies: dict[str, Any] = {}
        mod_summaries: list[dict[str, Any]] = []

        for mod in mods:
            mid = mod.get("id", "unknown")
            deps = mod.get("depends", {})
            if isinstance(deps, dict):
                dependencies.update(deps)
            eps = mod.get("entrypoints", {})
            if isinstance(eps, dict):
                for key, value in eps.items():
                    values = value if isinstance(value, list) else [value]
                    for item in values:
                        entrypoints.append({"mod_id": mid, "type": key, "value": item})
            mixins = mod.get("mixins", [])
            if isinstance(mixins, str):
                mixins = [mixins]
            if isinstance(mixins, list):
                for item in mixins:
                    if isinstance(item, str):
                        mixin_configs.add(item)
                    elif isinstance(item, dict) and isinstance(item.get("config"), str):
                        mixin_configs.add(item["config"])
            mod_summaries.append({
                "id": mid,
                "version": mod.get("version", "unknown"),
                "name": mod.get("name"),
                "environment": mod.get("environment", "*"),
                "authors": mod.get("authors", []),
                "depends": deps if isinstance(deps, dict) else {},
                "suggests": mod.get("suggests", {}),
            })

        mixin_classes: list[str] = []
        mixin_parse_errors: list[str] = []
        for config in sorted(mixin_configs):
            if config not in safe_names:
                mixin_parse_errors.append(f"Configuração ausente: {config}")
                continue
            try:
                raw = _read_json(zf, config)
                if isinstance(raw, dict):
                    package = raw.get("package", "")
                    for key in ("mixins", "client", "server"):
                        values = raw.get(key, [])
                        if isinstance(values, list):
                            for value in values:
                                if isinstance(value, str):
                                    mixin_classes.append(
                                        f"{package}.{value}" if package else value
                                    )
            except (ValueError, UnicodeDecodeError, KeyError, ScanError) as exc:
                mixin_parse_errors.append(f"{config}: {exc}")

        resource_files = [
            n for n in safe_names
            if n.startswith(("assets/", "data/")) or n == "pack.mcmeta"
        ]
        has_java_code = bool(all_classes)
        has_mixins = bool(mixin_configs)
        has_entrypoints = bool(entrypoints)
        native_payloads = [n for n in safe_names if n.lower().endswith((".so", ".dll", ".dylib"))]

        if not has_java_code and not has_entrypoints and not has_mixins:
            classification = "resource_candidate"
            explanation = "Não foram encontrados bytecode Java, entrypoints ou Mixins; revisar recursos antes de converter."
        elif has_mixins:
            classification = "requires_port_or_incompatible"
            explanation = "Declara Mixins; não pode ser executado diretamente pelo runtime nativo do Horizon."
        else:
            classification = "requires_port"
            explanation = "Contém código Java ou entrypoints; exige análise e portagem para APIs Horizon."

        return {
            "scanner": {"name": "HHRT Fabric Scanner", "version": "0.1.0"},
            "input": path,
            "format": "fabric-jar",
            "mods": mod_summaries,
            "dependencies": dependencies,
            "entrypoints": entrypoints,
            "mixin_configs": sorted(mixin_configs),
            "mixin_classes": sorted(set(mixin_classes)),
            "mixin_warnings": mixin_parse_errors,
            "statistics": {
                "archive_entries": len(infos),
                "safe_files": len(safe_names),
                "unsafe_paths_ignored": unsafe,
                "java_classes": len(all_classes),
                "resource_files": len(resource_files),
                "native_libraries": native_payloads,
            },
            "assessment": {
                "classification": classification,
                "direct_fabric_execution_supported": False,
                "explanation": explanation,
                "confidence": "heuristic",
            },
            "limitations": [
                "Análise estática; nenhum código Java é carregado ou executado.",
                "A presença de recursos não garante conversão fiel para .hmod.",
                "Dependências são listadas, mas não resolvidas automaticamente.",
                "Compatibilidade final depende da versão do Horizon e das APIs disponíveis.",
                "A detecção não substitui revisão manual de bytecode, chamadas e comportamento."
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analisa metadados e estrutura de um mod Fabric JAR sem executá-lo."
    )
    parser.add_argument("jar", help="Caminho do arquivo .jar")
    parser.add_argument("--json", action="store_true", help="Imprime relatório JSON")
    args = parser.parse_args()

    try:
        report = scan_jar(args.jar)
    except ScanError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("HHRT Fabric Scanner 0.1.0")
        print("=" * 28)
        for mod in report["mods"]:
            print(f"Mod: {mod['id']} {mod['version']}")
        print(f"Classes Java: {report['statistics']['java_classes']}")
        print(f"Arquivos de recursos: {report['statistics']['resource_files']}")
        print(f"Entrypoints: {len(report['entrypoints'])}")
        print(f"Mixins: {len(report['mixin_configs'])}")
        print(f"Classificação: {report['assessment']['classification']}")
        print(report["assessment"]["explanation"])
        print("\nAviso: classificação heurística; não representa garantia de compatibilidade.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
