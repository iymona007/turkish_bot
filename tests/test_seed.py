import json

from bot.config import LEVELS
from bot.words import SEED_PATH


def test_seed_is_valid_and_large_enough():
    data = json.loads(SEED_PATH.read_text(encoding="utf-8"))

    keys = [w["tr"].lower() for w in data]
    assert len(keys) == len(set(keys)), "takroriy turkcha so'z bor"

    for w in data:
        assert w["level"] in LEVELS
        for field in ("tr", "uz", "example_tr", "example_uz"):
            assert w[field].strip(), f"{w['tr']}: {field} bo'sh"

    for level in LEVELS:
        assert sum(w["level"] == level for w in data) >= 50
