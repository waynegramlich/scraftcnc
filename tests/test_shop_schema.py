"""Tests of `scraftcam.shop_schema`."""

import json
import re
import tomllib
import unittest

from scraftcam import shop_schema, shops


class SchemaTest(unittest.TestCase):
    """Tests of the schemas made from `shops.KINDS`."""

    def test_current(self) -> None:
        """The files in `scraftcam/schemas/` are what `KINDS` makes."""
        texts: dict[str, str] = shop_schema.schemas()
        on_disk: set[str] = {
            path.name for path in shop_schema.SCHEMA_DIRECTORY.glob("*.json")
        }
        self.assertEqual(on_disk, set(texts))
        name: str
        text: str
        for name, text in texts.items():
            path = shop_schema.SCHEMA_DIRECTORY / name
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                text,
                f"{name}: run `python3 -m scraftcam.shop_schema`",
            )
            json.loads(text)

    def test_examples(self) -> None:
        """Every measurement in every kind's example fits its pattern."""
        checked: int = 0
        kind: shops.TableKind
        for kind in shops.KINDS.values():
            example: dict[str, object] = tomllib.loads(kind.example)
            schema: shops.TableField
            for schema in shops.HEADER + kind.fields:
                value: object = example.get(schema.key)
                if schema.form in shops.UNITS and isinstance(value, str):
                    pattern: str = shop_schema.measurement_pattern(
                        shops.UNITS[schema.form]
                    )
                    self.assertIsNotNone(
                        re.fullmatch(pattern, value), (kind.kind, value)
                    )
                    checked += 1
        self.assertGreater(checked, 20)

    def test_patterns(self) -> None:
        """Measurements as catalogs write them; no unit is refused."""
        pattern: str = shop_schema.measurement_pattern(shops.LENGTH)
        good: str
        for good in ("1/4 in", "1-1/2 in", " .5in", "6 mm", "1e-3 in"):
            self.assertIsNotNone(re.fullmatch(pattern, good), good)
        bad: str
        for bad in ("1/4", "in", "1/4 inn", "5 rpm"):
            self.assertIsNone(re.fullmatch(pattern, bad), bad)
        self.assertEqual(
            shop_schema.schema_line("end_mill"),
            "#:schema " + shop_schema.SCHEMA_URL + "end_mill.json",
        )


if __name__ == "__main__":
    unittest.main()
