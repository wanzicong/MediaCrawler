from pathlib import Path

from mcp_server import data_reader


def test_find_data_files_maps_mcp_platform_code_to_store_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(data_reader, "DATA_DIR", str(tmp_path))
    output_dir = tmp_path / "douyin" / "jsonl"
    output_dir.mkdir(parents=True)
    output_file = output_dir / "search_contents_2026-07-28.jsonl"
    output_file.write_text('{"aweme_id":"1"}\n', encoding="utf-8")

    files = data_reader.find_data_files(
        "dy",
        "search",
        file_type="jsonl",
        date_str="2026-07-28",
    )

    assert files == {"contents": str(output_file)}


def test_read_jsonl_counts_all_rows_but_keeps_only_requested_items(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "items.jsonl"
    output_file.write_text(
        "".join(f'{{"id":{index}}}\n' for index in range(5)),
        encoding="utf-8",
    )

    result = data_reader.read_data_file(str(output_file), max_items=2)

    assert result["count"] == 5
    assert result["returned_count"] == 2
    assert result["truncated"] is True
    assert [item["id"] for item in result["items"]] == [0, 1]


def test_read_jsonl_keeps_valid_rows_and_reports_invalid_lines(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "items.jsonl"
    output_file.write_text(
        '{"id":1}\nnot-json\n{"id":2}\n',
        encoding="utf-8",
    )

    result = data_reader.read_data_file(str(output_file), max_items=10)

    assert result["count"] == 2
    assert result["returned_count"] == 2
    assert result["items"] == [{"id": 1}, {"id": 2}]
    assert "第 2 行" in result["error"]


def test_read_csv_counts_all_rows_but_keeps_only_requested_items(
    tmp_path: Path,
) -> None:
    output_file = tmp_path / "items.csv"
    output_file.write_text(
        "id,name\n1,one\n2,two\n3,three\n",
        encoding="utf-8",
    )

    result = data_reader.read_data_file(str(output_file), max_items=1)

    assert result["count"] == 3
    assert result["returned_count"] == 1
    assert result["truncated"] is True
    assert result["items"] == [{"id": "1", "name": "one"}]


def test_large_json_is_rejected_before_whole_file_load(
    tmp_path: Path,
    monkeypatch,
) -> None:
    output_file = tmp_path / "items.json"
    output_file.write_text('["payload"]', encoding="utf-8")
    monkeypatch.setattr(data_reader, "MAX_JSON_FILE_BYTES", 4)

    result = data_reader.read_data_file(str(output_file), max_items=1)

    assert result["count"] == 0
    assert result["returned_count"] == 0
    assert result["truncated"] is True
    assert result["items"] == []
    assert "JSONL" in result["error"]
