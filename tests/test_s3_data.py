from datetime import datetime, timezone
from pathlib import Path

import pytest

from fantasy_dashboard.s3_data import S3DataSyncError, synchronize_s3_data


class FakeS3Client:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.downloads: list[str] = []

    def list_objects_v2(self, **kwargs):
        prefix = kwargs["Prefix"]
        return {
            "IsTruncated": False,
            "Contents": [
                {
                    "Key": key,
                    "ETag": f'"etag-{len(value)}-{sum(value)}"',
                    "Size": len(value),
                    "LastModified": datetime(2026, 9, 23, tzinfo=timezone.utc),
                }
                for key, value in self.objects.items()
                if key.startswith(prefix)
            ],
        }

    def download_file(self, bucket: str, key: str, destination: str) -> None:
        del bucket
        self.downloads.append(key)
        Path(destination).write_bytes(self.objects[key])


def test_s3_sync_downloads_only_missing_or_changed_objects(tmp_path: Path) -> None:
    client = FakeS3Client(
        {
            "data/fantasy_dashboard.sqlite3": b"database-v1",
            "data/cache/regression/league.json": b"cache-v1",
        }
    )

    first = synchronize_s3_data("bucket", tmp_path, client=client)
    second = synchronize_s3_data("bucket", tmp_path, client=client)
    client.objects["data/cache/regression/league.json"] = b"cache-v2"
    client.objects["data/nfl_players.json"] = b"players"
    third = synchronize_s3_data("bucket", tmp_path, client=client)

    assert first.downloaded_objects == 2
    assert second.downloaded_objects == 0
    assert third.downloaded_objects == 2
    assert (tmp_path / "fantasy_dashboard.sqlite3").read_bytes() == b"database-v1"
    assert (tmp_path / "cache/regression/league.json").read_bytes() == b"cache-v2"
    assert (tmp_path / "nfl_players.json").read_bytes() == b"players"


def test_s3_sync_restores_a_missing_cached_file(tmp_path: Path) -> None:
    client = FakeS3Client({"data/nfl_players.json": b"players"})
    synchronize_s3_data("bucket", tmp_path, client=client)
    (tmp_path / "nfl_players.json").unlink()

    result = synchronize_s3_data("bucket", tmp_path, client=client)

    assert result.downloaded_objects == 1
    assert (tmp_path / "nfl_players.json").read_bytes() == b"players"


def test_s3_sync_rejects_an_empty_prefix(tmp_path: Path) -> None:
    client = FakeS3Client({"other/file.json": b"value"})

    with pytest.raises(S3DataSyncError, match="No objects found"):
        synchronize_s3_data("bucket", tmp_path, client=client)
