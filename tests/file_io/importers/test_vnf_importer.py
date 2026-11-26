"""Compatibility regressions for VNF section dispatch."""

from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from pyptp.IO.importers.vnf_importer import VnfImporter


class TestVnfImporter(unittest.TestCase):
    def _dispatch(self, raw_text: str) -> list[tuple[str, str]]:
        recorder = Mock()
        handlers = {
            name: getattr(recorder, name)
            for name in ("NODE", "CABLE", "SPECIAL TRANSFORMER")
        }
        with (
            patch.object(VnfImporter, "_HANDLERS", handlers),
            patch.object(
                VnfImporter, "_get_and_migrate_vnf_content", return_value=raw_text
            ),
        ):
            network = VnfImporter().import_vnf("test.vnf")
        for recorded_call in recorder.mock_calls:
            self.assertIs(recorded_call.args[0], network)
        return [
            (recorded_call[0].removesuffix(".handle"), recorded_call.args[1])
            for recorded_call in recorder.mock_calls
        ]

    def test_registry_order_and_repeated_sections(self) -> None:
        raw_text = "[CABLE]\nfirst cable\n[NODE]\nfirst node\n[CABLE]\nsecond cable\n[NODE]\nsecond node"
        self.assertEqual(
            self._dispatch(raw_text),
            [
                ("NODE", "first node\n#END"),
                ("NODE", "second node\n#END"),
                ("CABLE", "first cable\n#END"),
                ("CABLE", "second cable\n#END"),
            ],
        )

    def test_unknown_and_malformed_headers_terminate_bodies(self) -> None:
        raw_text = "[NODE]\nfirst\n[UNKNOWN]\nignored\n[NODE]\nsecond\n[]\nignored\n[NODE]\nthird\n[malformed"
        self.assertEqual(
            self._dispatch(raw_text),
            [
                ("NODE", "first\n#END"),
                ("NODE", "second\n#END"),
                ("NODE", "third\n#END"),
            ],
        )

    def test_whitespace_and_eof_normalization(self) -> None:
        cases = [
            ("[NODE]\nvalue", "value\n#END"),
            ("[NODE]\nvalue\n", "value\n#END"),
            ("[NODE]\nvalue  \t\n\n", "value\n#END"),
            ("[NODE]\r\nvalue  \t\r\n", "\nvalue\n#END"),
            ("[NODE]\tvalue", "value\n#END"),
            ("[NODE]\n\nvalue", "\nvalue\n#END"),
        ]
        for raw_text, chunk in cases:
            with self.subTest(raw_text=raw_text):
                self.assertEqual(self._dispatch(raw_text), [("NODE", chunk)])

    def test_empty_sections_preserve_legacy_follow_on_matches(self) -> None:
        cases = [
            ("", []),
            ("[UNKNOWN]\nignored", []),
            ("[NODE]\n", [("NODE", "\n#END")]),
            (
                "[NODE]\n[NODE]\n",
                [("NODE", "\n#END"), ("NODE", "[NODE]\n#END"), ("NODE", "\n#END")],
            ),
            (
                "[NODE]\n[CABLE]\n",
                [("NODE", "\n#END"), ("NODE", "[CABLE]\n#END"), ("CABLE", "\n#END")],
            ),
            (
                "[NODE]\n[UNKNOWN]\nignored\n",
                [("NODE", "\n#END"), ("NODE", "[UNKNOWN]\nignored\n#END")],
            ),
            (
                "[NODE]\n[NODE]\n[NODE]\nbody",
                [
                    ("NODE", "\n#END"),
                    ("NODE", "[NODE]\n#END"),
                    ("NODE", "\n#END"),
                    ("NODE", "[NODE]\nbody\n#END"),
                ],
            ),
        ]
        for raw_text, expected in cases:
            with self.subTest(raw_text=raw_text):
                self.assertEqual(self._dispatch(raw_text), expected)

    def test_inline_headers_remain_unanchored(self) -> None:
        self.assertEqual(
            self._dispatch("prefix [NODE]\none [NODE]\ntwo [CABLE]\nwire\n"),
            [("NODE", "one [NODE]\ntwo [CABLE]\nwire\n#END"), ("CABLE", "wire\n#END")],
        )
        self.assertEqual(self._dispatch("[[NODE]\nbody\n"), [("NODE", "body\n#END")])

    def test_header_names_case_and_required_whitespace(self) -> None:
        self.assertEqual(
            self._dispatch(
                "[node]\nignored\n[NODE]without whitespace\n[NODEX]\nignored\n"
                "[SPECIAL TRANSFORMER]\ntransformer\n[NODE]\tnode"
            ),
            [("NODE", "node\n#END"), ("SPECIAL TRANSFORMER", "transformer\n#END")],
        )
        self.assertEqual(self._dispatch("[NODE]"), [])
