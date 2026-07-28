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
