from __future__ import annotations

import json

import pytest

from pyjev.batch import BatchRecord, BatchResult, BatchSummary
from pyjev.output import OutputPathError, format_json, format_jsonl, format_markdown, pluck


def test_pluck_supports_dotted_keys_and_array_indexes():
    data = {"results": [{"verdict": "verified"}, {"verdict": "unsupported"}], "metrics": {"confidence": 0.8}}
    assert pluck(data, "results[1].verdict") == "unsupported"
    assert pluck(data, "metrics.confidence") == 0.8
    assert pluck(["zero", "one"], "[1]") == "one"


@pytest.mark.parametrize(
    "path",
    ["", "missing.key", "results[5]", "results[x]", "results..verdict", "results[0"],
)
def test_pluck_errors_on_invalid_or_missing_paths(path: str):
    with pytest.raises(OutputPathError):
        pluck({"results": [{"verdict": "verified"}]}, path)


def test_public_json_format_uses_result_dictionary_shape():
    class Result:
        def to_dict(self):
            return {"value": "yes", "confidence": 0.9}

    assert json.loads(format_json(Result())) == {"value": "yes", "confidence": 0.9}


def test_jsonl_formats_one_batch_record_per_line():
    batch = BatchResult(
        records=(
            BatchRecord(0, "first", True, {"value": 1}, None),
            BatchRecord(1, "second", False, None, None),
        ),
        summary=BatchSummary(2, 1, 1, 3, 2),
    )
    lines = format_jsonl(batch).splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == "first"
    assert json.loads(lines[1])["ok"] is False


def test_markdown_summary_shows_metrics_and_records_without_model_interpretation():
    batch = BatchResult(
        records=(BatchRecord(0, "first", True, {"value": "some result"}, None),),
        summary=BatchSummary(1, 1, 0, 3, 2),
    )
    rendered = format_markdown(batch, title="Batch run")
    assert "# Batch run" in rendered
    assert "| input_tokens | 3 |" in rendered
    assert "| 0 | first | True | null |" in rendered
    assert "some result" not in rendered
