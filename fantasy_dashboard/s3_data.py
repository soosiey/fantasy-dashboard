import json
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Any

SYNC_STATE_FILENAME = ".s3-sync-state.json"


class S3DataSyncError(RuntimeError):
    """Raised when the S3-backed runtime data directory cannot be refreshed."""


@dataclass(frozen=True, slots=True)
class S3ObjectState:
    etag: str
    size: int
    last_modified: str


@dataclass(frozen=True, slots=True)
class S3SyncResult:
    data_dir: Path
    remote_objects: int
    downloaded_objects: int


def _normalized_prefix(prefix: str) -> str:
    value = prefix.strip().strip("/")
    return f"{value}/" if value else ""


def _relative_object_path(key: str, prefix: str) -> Path | None:
    if not key.startswith(prefix):
        return None
    relative = PurePosixPath(key[len(prefix) :])
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        return None
    return Path(*relative.parts)


def _read_sync_state(path: Path) -> dict[str, S3ObjectState]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        objects = payload.get("objects", {})
        return {
            key: S3ObjectState(
                etag=str(value["etag"]),
                size=int(value["size"]),
                last_modified=str(value["last_modified"]),
            )
            for key, value in objects.items()
            if isinstance(value, dict)
        }
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _write_sync_state(path: Path, objects: dict[str, S3ObjectState]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            json.dump(
                {"objects": {key: asdict(value) for key, value in objects.items()}},
                temporary_file,
                sort_keys=True,
                separators=(",", ":"),
            )
            temporary_path = Path(temporary_file.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _list_objects(client: Any, bucket: str, prefix: str) -> dict[str, S3ObjectState]:
    objects: dict[str, S3ObjectState] = {}
    continuation_token: str | None = None
    while True:
        arguments: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if continuation_token:
            arguments["ContinuationToken"] = continuation_token
        response = client.list_objects_v2(**arguments)
        for item in response.get("Contents", []):
            key = str(item.get("Key") or "")
            if not key or key.endswith("/"):
                continue
            last_modified = item.get("LastModified")
            objects[key] = S3ObjectState(
                etag=str(item.get("ETag") or "").strip('"'),
                size=int(item.get("Size") or 0),
                last_modified=(
                    last_modified.isoformat()
                    if hasattr(last_modified, "isoformat")
                    else str(last_modified or "")
                ),
            )
        if not response.get("IsTruncated"):
            return objects
        continuation_token = response.get("NextContinuationToken")
        if not continuation_token:
            return objects


def _create_s3_client(
    *,
    region_name: str | None,
    access_key_id: str | None,
    secret_access_key: str | None,
):
    try:
        import boto3
    except ImportError as error:
        raise S3DataSyncError(
            "boto3 is required when S3 data synchronization is configured"
        ) from error
    arguments = {
        "region_name": region_name or None,
        "aws_access_key_id": access_key_id or None,
        "aws_secret_access_key": secret_access_key or None,
    }
    return boto3.client(
        "s3",
        **{key: value for key, value in arguments.items() if value is not None},
    )


def synchronize_s3_data(
    bucket: str,
    cache_dir: Path,
    *,
    prefix: str = "data/",
    region_name: str | None = None,
    access_key_id: str | None = None,
    secret_access_key: str | None = None,
    client: Any | None = None,
) -> S3SyncResult:
    """Mirror missing or changed S3 objects into an ephemeral runtime directory."""
    if not bucket.strip():
        raise ValueError("bucket must not be empty")
    normalized_prefix = _normalized_prefix(prefix)
    destination = Path(cache_dir)
    state_path = destination / SYNC_STATE_FILENAME
    s3_client = client or _create_s3_client(
        region_name=region_name,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
    )
    try:
        remote_objects = _list_objects(s3_client, bucket, normalized_prefix)
        if not remote_objects:
            raise S3DataSyncError(
                f"No objects found at s3://{bucket}/{normalized_prefix}"
            )
        previous_objects = _read_sync_state(state_path)
        downloaded = 0
        for key, remote_state in remote_objects.items():
            relative_path = _relative_object_path(key, normalized_prefix)
            if relative_path is None:
                continue
            local_path = destination / relative_path
            if local_path.is_file() and previous_objects.get(key) == remote_state:
                continue
            local_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = local_path.with_name(f".{local_path.name}.s3-download")
            try:
                s3_client.download_file(bucket, key, str(temporary_path))
                temporary_path.replace(local_path)
            finally:
                temporary_path.unlink(missing_ok=True)
            downloaded += 1
        _write_sync_state(state_path, remote_objects)
    except S3DataSyncError:
        raise
    except Exception as error:
        raise S3DataSyncError(f"Unable to synchronize S3 data: {error}") from error
    return S3SyncResult(
        data_dir=destination,
        remote_objects=len(remote_objects),
        downloaded_objects=downloaded,
    )


def has_cached_s3_data(cache_dir: Path) -> bool:
    path = Path(cache_dir)
    return path.is_dir() and any(
        item.is_file() and item.name != SYNC_STATE_FILENAME for item in path.rglob("*")
    )
