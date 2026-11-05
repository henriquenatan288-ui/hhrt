from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import tomllib

from scanner.hhrt_scanner import ScanError, scan_jar
from converter.hhrt_convert import ConvertError, convert_jar


class FabricScannerPipelineTests(unittest.TestCase):
    def make_jar(self, root: Path, name: str, entries: dict[str, bytes]) -> Path:
        path = root / name
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as jar:
            for entry_name, content in entries.items():
                jar.writestr(entry_name, content)
        return path

    def base_metadata(self, **overrides):
        metadata = {
            "schemaVersion": 1,
            "id": "demo_mod",
            "version": "1.0.0",
            "name": "Demo Mod",
            "description": "A resource-only test mod",
            "authors": ["HHRT test"],
            "depends": {"minecraft": ">=1.21", "fabricloader": ">=0.16"},
        }
        metadata.update(overrides)
        return json.dumps(metadata).encode("utf-8")

    def resource_entries(self):
        return {
            "fabric.mod.json": self.base_metadata(),
            "assets/demo_mod/lang/en_us.json": b'{"item.demo_mod.test":"Test"}',
            "assets/demo_mod/textures/item/test.png": b"fake-png-fixture",
            "data/demo_mod/recipe/test.json": b'{"type":"minecraft:crafting_shapeless"}',
            "data/minecraft/tags/item/test.json": b'{"replace":false,"values":[]}',
        }

    def test_resource_only_jar_is_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            jar = self.make_jar(Path(temp), "resource.jar", self.resource_entries())
            report = scan_jar(str(jar))
            self.assertEqual(report["assessment"]["classification"], "resource_candidate")
            self.assertEqual(report["statistics"]["java_classes"], 0)
            self.assertEqual(report["statistics"]["resource_files"], 4)

    def test_empty_jar_is_not_resource_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            jar = self.make_jar(
                Path(temp), "empty.jar", {"fabric.mod.json": self.base_metadata()}
            )
            report = scan_jar(str(jar))
            self.assertEqual(
                report["assessment"]["classification"], "no_portable_content"
            )

    def test_nested_jar_requires_port(self):
        with tempfile.TemporaryDirectory() as temp:
            entries = self.resource_entries()
            entries["META-INF/jars/library.jar"] = b"nested-jar"
            jar = self.make_jar(Path(temp), "nested.jar", entries)
            report = scan_jar(str(jar))
            self.assertEqual(report["assessment"]["classification"], "requires_port")
            self.assertEqual(
                report["statistics"]["nested_jars"], ["META-INF/jars/library.jar"]
            )

    def test_java_class_requires_port(self):
        with tempfile.TemporaryDirectory() as temp:
            entries = self.resource_entries()
            entries["demo/Feature.class"] = b"not-real-bytecode"
            jar = self.make_jar(Path(temp), "coded.jar", entries)
            report = scan_jar(str(jar))
            self.assertEqual(report["assessment"]["classification"], "requires_port")

    def test_mixin_is_not_convertible(self):
        with tempfile.TemporaryDirectory() as temp:
            entries = self.resource_entries()
            meta = json.loads(entries["fabric.mod.json"])
            meta["mixins"] = ["demo.mixins.json"]
            entries["fabric.mod.json"] = json.dumps(meta).encode()
            entries["demo.mixins.json"] = b'{"package":"demo.mixin","mixins":["ExampleMixin"]}'
            entries["demo/mixin/ExampleMixin.class"] = b"not-real-bytecode"
            jar = self.make_jar(Path(temp), "mixin.jar", entries)
            with self.assertRaises(ConvertError):
                convert_jar(jar, Path(temp) / "out.hmod")

    def test_converter_creates_hmod_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            jar = self.make_jar(root, "resource.jar", self.resource_entries())
            output = root / "converted.hmod"
            result = convert_jar(jar, output, side="both")
            self.assertTrue(output.is_file())
            self.assertEqual(result["files_copied"], 4)
            with zipfile.ZipFile(output) as hmod:
                self.assertIn("horizon-mod.toml", hmod.namelist())
                self.assertIn("assets/demo_mod/lang/en_us.json", hmod.namelist())
                self.assertIn("data/demo_mod/recipe/test.json", hmod.namelist())
                manifest = tomllib.loads(hmod.read("horizon-mod.toml").decode())
                self.assertEqual(manifest["id"], "demo_mod")
                self.assertEqual(manifest["api"], "0.2")
                self.assertEqual(manifest["capabilities"], ["registries"])
                self.assertEqual(manifest["side"], "both")

    def test_converter_rejects_code_mod(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entries = self.resource_entries()
            entries["demo/Feature.class"] = b"not-real-bytecode"
            jar = self.make_jar(root, "coded.jar", entries)
            with self.assertRaises(ConvertError):
                convert_jar(jar, root / "out.hmod")

    def test_converter_rejects_untranslated_dependency(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            metadata = self.base_metadata(depends={
                "minecraft": ">=1.21",
                "fabricloader": ">=0.16",
                "another_mod": "*",
            })
            entries = self.resource_entries()
            entries["fabric.mod.json"] = metadata
            jar = self.make_jar(root, "dependency.jar", entries)
            with self.assertRaises(ConvertError):
                convert_jar(jar, root / "out.hmod")

    def test_converter_rejects_non_tag_minecraft_namespace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            entries = self.resource_entries()
            entries["assets/minecraft/textures/item/override.png"] = b"not-a-png"
            jar = self.make_jar(root, "override.jar", entries)
            with self.assertRaises(ConvertError):
                convert_jar(jar, root / "out.hmod")

    def test_bad_jar_reports_scan_error(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "not-a-jar.jar"
            path.write_bytes(b"not a zip")
            with self.assertRaises(ScanError):
                scan_jar(str(path))


if __name__ == "__main__":
    unittest.main()
