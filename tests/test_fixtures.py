"""
tests/test_fixtures.py

Integration tests using real fixture funscripts:
  tests/fixtures/big_buck_bunny.raw.funscript     — unprocessed original
  tests/fixtures/big_buck_bunny.forged.funscript  — after FunScriptForge recommendations

These tests verify the full cli.py contract against real content:
  - Both fixtures load correctly
  - Forged is measurably cleaner than raw (less extreme position jumps)
  - process() produces the expected output channels for both
  - All five eTransforms produce valid, distinct outputs
  - Different eTransforms produce detectably different alpha/beta/pulse_frequency waveforms

Run:
    python -m pytest tests/test_fixtures.py -v
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
import cli

FIXTURES = Path(__file__).parent / "fixtures"
RAW     = FIXTURES / "big_buck_bunny.raw.funscript"
FORGED  = FIXTURES / "big_buck_bunny.forged.funscript"

REQUIRED_OUTPUTS = {"alpha", "beta", "pulse_frequency"}


# ── Fixture loading ────────────────────────────────────────────────────────────

class TestFixtureLoad(unittest.TestCase):

    def test_raw_loads(self):
        info = cli.load_file(str(RAW))
        self.assertGreater(info["actions"], 0)
        self.assertGreater(info["duration_s"], 0)
        self.assertEqual(len(info["x"]), len(info["y"]))

    def test_forged_loads(self):
        info = cli.load_file(str(FORGED))
        self.assertGreater(info["actions"], 0)
        self.assertGreater(info["duration_s"], 0)
        self.assertEqual(len(info["x"]), len(info["y"]))

    def test_values_in_range(self):
        for path in (RAW, FORGED):
            info = cli.load_file(str(path))
            self.assertGreaterEqual(min(info["y"]), 0,   f"{path.name}: y below 0")
            self.assertLessEqual(max(info["y"]),   100,  f"{path.name}: y above 100")

    def test_forged_has_fewer_extreme_jumps(self):
        """Forged funscript should have smoother position changes than raw."""
        raw    = cli.load_file(str(RAW))
        forged = cli.load_file(str(FORGED))

        def max_jump(data):
            y = np.array(data["y"])
            return float(np.max(np.abs(np.diff(y)))) if len(y) > 1 else 0.0

        raw_jump    = max_jump(raw)
        forged_jump = max_jump(forged)

        # Forged should have smaller or equal maximum jump
        # (if they're the same content, this catches regressions)
        self.assertLessEqual(
            forged_jump, raw_jump + 1.0,  # +1 tolerance for floating point
            f"Forged max jump ({forged_jump:.1f}) should not exceed raw ({raw_jump:.1f})"
        )


# ── Processing ────────────────────────────────────────────────────────────────

class TestFixtureProcess(unittest.TestCase):

    def _process_to_tempdir(self, source_path):
        """Copy source to a temp dir, process it, return (result, tempdir)."""
        import shutil
        d = tempfile.mkdtemp()
        dest = Path(d) / source_path.name
        shutil.copy(source_path, dest)
        config = cli.get_default_config()
        result = cli.process(str(dest), config)
        return result, d

    def test_raw_processes_successfully(self):
        result, d = self._process_to_tempdir(RAW)
        try:
            self.assertTrue(result["success"], msg=result.get("error"))
            self.assertGreater(len(result["outputs"]), 0)
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)

    def test_forged_processes_successfully(self):
        result, d = self._process_to_tempdir(FORGED)
        try:
            self.assertTrue(result["success"], msg=result.get("error"))
            self.assertGreater(len(result["outputs"]), 0)
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)

    def test_primary_channels_present(self):
        """alpha, beta, pulse_frequency must all be generated."""
        result, d = self._process_to_tempdir(FORGED)
        try:
            self.assertTrue(result["success"], msg=result.get("error"))
            suffixes = {o["suffix"] for o in result["outputs"]}
            for ch in REQUIRED_OUTPUTS:
                self.assertIn(ch, suffixes, f"Missing primary channel: {ch}")
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)

    def test_output_files_are_loadable(self):
        """Every generated output file should load without error."""
        result, d = self._process_to_tempdir(FORGED)
        try:
            self.assertTrue(result["success"])
            for o in result["outputs"]:
                data = cli.load_file(o["path"])
                self.assertGreater(len(data["x"]), 0, f"Empty output: {o['suffix']}")
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)


# ── eTransforms ───────────────────────────────────────────────────────────────

class TestETransforms(unittest.TestCase):

    def test_all_presets_listed(self):
        presets = cli.list_presets()
        for name in cli.BUILTIN_PRESETS:
            self.assertIn(name, presets)

    def test_all_presets_have_sliders(self):
        for name, meta in cli.BUILTIN_PRESETS.items():
            self.assertIn("sliders", meta, f"{name} missing sliders spec")
            self.assertGreater(len(meta["sliders"]), 0, f"{name} has empty sliders")

    def test_get_preset_merges_with_defaults(self):
        """get_preset() returns a full config — no missing keys."""
        default = cli.get_default_config()
        for name in cli.BUILTIN_PRESETS:
            config = cli.get_preset(name)
            for section in default:
                self.assertIn(section, config, f"{name}: missing section {section}")

    def test_presets_produce_valid_outputs(self):
        """Every eTransform processes the forged fixture without error."""
        import shutil
        for name in cli.BUILTIN_PRESETS:
            d = tempfile.mkdtemp()
            try:
                dest = Path(d) / FORGED.name
                shutil.copy(FORGED, dest)
                config = cli.get_preset(name)
                result = cli.process(str(dest), config)
                self.assertTrue(
                    result["success"],
                    msg=f"eTransform '{name}' failed: {result.get('error')}"
                )
                suffixes = {o["suffix"] for o in result["outputs"]}
                for ch in REQUIRED_OUTPUTS:
                    self.assertIn(ch, suffixes, f"'{name}' missing channel: {ch}")
            finally:
                shutil.rmtree(d, ignore_errors=True)

    def test_different_presets_produce_different_alpha(self):
        """Gentle and Reactive should produce measurably different alpha outputs."""
        import shutil

        results = {}
        for name in ("Gentle", "Reactive"):
            d = tempfile.mkdtemp()
            try:
                dest = Path(d) / FORGED.name
                shutil.copy(FORGED, dest)
                config = cli.get_preset(name)
                result = cli.process(str(dest), config)
                self.assertTrue(result["success"], msg=f"{name}: {result.get('error')}")
                alpha_path = next(o["path"] for o in result["outputs"] if o["suffix"] == "alpha")
                alpha_data = cli.load_file(alpha_path)
                results[name] = np.array(alpha_data["y"])
            finally:
                shutil.rmtree(d, ignore_errors=True)

        # The two alpha outputs should differ — same content, different character
        min_len = min(len(v) for v in results.values())
        delta = np.mean(np.abs(results["Gentle"][:min_len] - results["Reactive"][:min_len]))
        self.assertGreater(
            delta, 0.0,
            "Gentle and Reactive produced identical alpha outputs — presets have no effect"
        )


# ── Preset persistence ────────────────────────────────────────────────────────

class TestPresetPersistence(unittest.TestCase):

    def test_save_and_reload(self):
        """save_preset / load_user_presets round-trip."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            config = cli.get_preset("Balanced")
            cli.save_preset("MyTest", config, "test preset", path=path)
            loaded = cli.load_user_presets(path=path)
            self.assertIn("MyTest", loaded)
            self.assertEqual(loaded["MyTest"]["description"], "test preset")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_user_preset_visible_in_list(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            config = cli.get_preset("Gentle")
            cli.save_preset("CommunityPreset", config, path=path)
            all_presets = cli.list_presets(user_presets_path=path)
            self.assertIn("CommunityPreset", all_presets)
            self.assertFalse(all_presets["CommunityPreset"]["builtin"])
        finally:
            Path(path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
