import json

from fastapi.testclient import TestClient

import api.routers.data as data_router
from api.main import app


def test_jsonl_is_listed_counted_and_previewed(
    tmp_path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "data"
    output_dir = data_dir / "douyin" / "jsonl"
    output_dir.mkdir(parents=True)
    action_file = output_dir / "liked_user_actions_2026-07-28.jsonl"
    rows = [
        {
            "account_hash": "hash",
            "aweme_id": "1",
            "action_type": "liked",
            "observed_ts": 1,
        },
        {
            "account_hash": "hash",
            "aweme_id": "2",
            "action_type": "liked",
            "observed_ts": 2,
        },
    ]
    action_file.write_text(
        "\n".join(json.dumps(item) for item in rows) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(data_router, "DATA_DIR", data_dir)
    client = TestClient(app)

    listed = client.get("/api/data/files")
    filtered = client.get("/api/data/files", params={"platform": "dy"})
    stats = client.get("/api/data/stats")
    assert listed.status_code == 200
    assert listed.json()["files"][0]["name"] == action_file.name
    assert listed.json()["files"][0]["record_count"] == 2
    assert filtered.status_code == 200
    assert [item["name"] for item in filtered.json()["files"]] == [
        action_file.name
    ]
    assert stats.status_code == 200
    assert stats.json()["by_platform"]["dy"] == 1
    assert stats.json()["by_type"]["jsonl"] == 1

    preview = client.get(
        "/api/data/files/douyin/jsonl/"
        "liked_user_actions_2026-07-28.jsonl",
        params={"limit": 1},
    )
    assert preview.status_code == 200
    assert preview.json() == {"data": rows[:1], "total": 2}


def test_invalid_jsonl_returns_line_number(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    output_dir = data_dir / "douyin" / "jsonl"
    output_dir.mkdir(parents=True)
    (output_dir / "collected_user_actions_bad.jsonl").write_text(
        '{"aweme_id": "1"}\nnot-json\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(data_router, "DATA_DIR", data_dir)
    client = TestClient(app)

    response = client.get(
        "/api/data/files/douyin/jsonl/"
        "collected_user_actions_bad.jsonl"
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid JSONL at line 2"


def test_media_transcript_is_attributed_to_its_platform(
    tmp_path,
    monkeypatch,
) -> None:
    data_dir = tmp_path / "data"
    transcript_dir = (
        data_dir
        / "media"
        / "dy"
        / "123"
        / "transcripts"
        / "transcribe_test"
    )
    transcript_dir.mkdir(parents=True)
    transcript_path = transcript_dir / "transcript.json"
    transcript_path.write_text(
        json.dumps({"content_id": "123", "full_text": "测试"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(data_router, "DATA_DIR", data_dir)
    client = TestClient(app)

    filtered = client.get("/api/data/files", params={"platform": "dy"})
    stats = client.get("/api/data/stats")

    assert filtered.status_code == 200
    assert [
        item["path"].replace("\\", "/")
        for item in filtered.json()["files"]
    ] == [
        "media/dy/123/transcripts/transcribe_test/transcript.json"
    ]
    assert stats.status_code == 200
    assert stats.json()["by_platform"]["dy"] == 1


def test_excel_preview_defaults_to_user_actions_sheet(
    tmp_path,
    monkeypatch,
) -> None:
    from openpyxl import Workbook

    data_dir = tmp_path / "data"
    output_dir = data_dir / "douyin" / "excel"
    output_dir.mkdir(parents=True)
    excel_path = output_dir / "douyin_liked.xlsx"
    workbook = Workbook()
    contents = workbook.active
    contents.title = "Contents"
    contents.append(["aweme_id"])
    contents.append(["content-1"])
    actions = workbook.create_sheet("UserActions")
    actions.append(["account_hash", "aweme_id", "action_type", "observed_ts"])
    actions.append(["hash", "action-1", "liked", 1])
    workbook.save(excel_path)
    monkeypatch.setattr(data_router, "DATA_DIR", data_dir)
    client = TestClient(app)

    default_preview = client.get(
        "/api/data/files/douyin/excel/douyin_liked.xlsx"
    )
    contents_preview = client.get(
        "/api/data/files/douyin/excel/douyin_liked.xlsx",
        params={"sheet": "Contents"},
    )

    assert default_preview.status_code == 200
    assert default_preview.json()["sheet"] == "UserActions"
    assert default_preview.json()["data"][0]["action_type"] == "liked"
    assert contents_preview.status_code == 200
    assert contents_preview.json()["sheet"] == "Contents"
