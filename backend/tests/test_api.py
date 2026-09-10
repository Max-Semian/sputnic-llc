"""API contract tests.

These pin the externally visible behaviour of the refactored backend to the
original business logic and guard the fixed bugs:

* empty / oversized uploads return clean HTTP errors and leave no files behind;
* deleting a file with alerts succeeds and cascades the alerts (was HTTP 500);
* the download endpoint 404s when the stored bytes are missing;
* ``title`` length is validated with HTTP 422 instead of a DB-level 500.
"""

from datetime import datetime, timedelta, timezone

from src.domain.entities import Alert, StoredFile


async def _upload(client, name="hello.txt", content=b"hello\n", mime="text/plain"):
    return await client.post(
        "/files",
        data={"title": "Договор"},
        files={"file": (name, content, mime)},
    )


async def _insert_file(client, *, file_id: str, created_at: datetime, title="x"):
    factory = client.app.state.session_factory
    async with factory() as session:
        session.add(
            StoredFile(
                id=file_id,
                title=title,
                original_name=f"{file_id}.txt",
                stored_name=f"{file_id}.txt",
                mime_type="text/plain",
                size=3,
                processing_status="uploaded",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await session.commit()


async def test_upload_clean_file_creates_record_and_enqueues(client):
    response = await _upload(client, content=b"hello world\nline two\n")
    assert response.status_code == 201
    body = response.json()

    assert body["title"] == "Договор"
    assert body["original_name"] == "hello.txt"
    assert body["mime_type"] == "text/plain"
    assert body["size"] == 21
    assert body["processing_status"] == "uploaded"
    assert body["scan_status"] is None
    assert body["requires_attention"] is False
    assert client.enqueued == [body["id"]]

    # physical bytes are on disk inside the storage directory
    storage = client.app.state.storage
    assert storage.exists(body["id"] + ".txt")


async def test_upload_empty_file_returns_400(client):
    response = await _upload(client, content=b"")
    assert response.status_code == 400
    assert response.json()["detail"] == "File is empty"
    assert list((client.app.state.storage.root).iterdir()) == []


async def test_upload_too_large_returns_413_and_leaves_no_files(client):
    # max_upload_size is 1 MB in the test app; send ~2 MB
    response = await _upload(client, content=b"x" * (2 * 1024 * 1024))
    assert response.status_code == 413
    assert "maximum allowed size" in response.json()["detail"]
    assert list((client.app.state.storage.root).iterdir()) == []


async def test_empty_list_endpoints(client):
    files = await client.get("/files")
    assert files.status_code == 200
    assert files.json() == []
    alerts = await client.get("/alerts")
    assert alerts.status_code == 200
    assert alerts.json() == []


async def test_get_file_returns_404_for_missing(client):
    missing = await client.get("/files/00000000-0000-4000-8000-000000000000")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "File not found"


async def test_update_file_title(client):
    created = await _upload(client)
    file_id = created.json()["id"]

    ok = await client.patch(f"/files/{file_id}", json={"title": "Новое название"})
    assert ok.status_code == 200
    assert ok.json()["title"] == "Новое название"

    not_found = await client.patch(
        "/files/00000000-0000-4000-8000-000000000000", json={"title": "x"}
    )
    assert not_found.status_code == 404


async def test_update_file_validates_title_length(client):
    created = await _upload(client)
    file_id = created.json()["id"]

    too_long = await client.patch(f"/files/{file_id}", json={"title": "x" * 256})
    assert too_long.status_code == 422

    empty = await client.patch(f"/files/{file_id}", json={"title": ""})
    assert empty.status_code == 422

    # record is untouched
    current = await client.get(f"/files/{file_id}")
    assert current.json()["title"] == "Договор"


async def test_delete_file_with_alerts_cascades(client):
    """Regression: deleting a processed file used to raise FK IntegrityError.

    The physical file was removed first and the row deletion then failed with
    an HTTP 500, orphaning the stored bytes.
    """
    created = await _upload(client)
    file_id = created.json()["id"]

    factory = client.app.state.session_factory
    async with factory() as session:
        session.add(Alert(file_id=file_id, level="info", message="File processed successfully"))
        await session.commit()

    alerts = await client.get("/alerts")
    assert any(a["file_id"] == file_id for a in alerts.json())

    deleted = await client.delete(f"/files/{file_id}")
    assert deleted.status_code == 204

    assert (await client.get(f"/files/{file_id}")).status_code == 404
    alerts_after = (await client.get("/alerts")).json()
    assert not any(a["file_id"] == file_id for a in alerts_after)
    storage = client.app.state.storage
    assert not list(storage.root.iterdir())

    # second delete -> 404
    assert (await client.delete(f"/files/{file_id}")).status_code == 404


async def test_download_returns_file_content(client):
    content = b"plain text content"
    created = await _upload(client, content=content)
    file_id = created.json()["id"]

    download = await client.get(f"/files/{file_id}/download")
    assert download.status_code == 200
    assert download.content == content
    assert download.headers["content-type"].startswith("text/plain")
    assert "hello.txt" in download.headers["content-disposition"]


async def test_download_404_when_stored_bytes_missing(client):
    created = await _upload(client)
    file_id = created.json()["id"]

    storage = client.app.state.storage
    for stored in storage.root.iterdir():
        stored.unlink()

    download = await client.get(f"/files/{file_id}/download")
    assert download.status_code == 404
    assert download.json()["detail"] == "Stored file not found"


async def test_files_listed_newest_first(client):
    now = datetime.now(timezone.utc)
    older_id = "10000000-0000-4000-8000-000000000001"
    newer_id = "20000000-0000-4000-8000-000000000002"
    await _insert_file(client, file_id=older_id, created_at=now - timedelta(hours=2))
    await _insert_file(client, file_id=newer_id, created_at=now - timedelta(hours=1))

    body = (await client.get("/files")).json()
    assert [f["id"] for f in body] == [newer_id, older_id]

