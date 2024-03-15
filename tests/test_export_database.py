from datasette.app import Datasette
import pytest
import shutil
import sqlite3


@pytest.fixture
def db_path(tmpdir):
    path = str(tmpdir / "data.db")
    conn = sqlite3.connect(path)
    with conn:
        conn.execute("create table big (id integer primary key, string text)")
        conn.executemany(
            "insert into big (string) values (?)",
            (["12349871243987213948 " * 100] for i in range(1001)),
        )
    return path


@pytest.mark.asyncio
async def test_permissions(db_path, tmpdir):
    datasette = Datasette([db_path])
    anon_response1 = await datasette.client.get("/data/-/export-database")
    assert anon_response1.status_code == 403
    anon_response2 = await datasette.client.get("/data")
    assert "/export-database" not in anon_response2.text
    # Now get the signed URL
    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    root_response1 = await datasette.client.get("/data", cookies=cookies)
    cookies["ds_csrftoken"] = root_response1.cookies["ds_csrftoken"]
    assert "/export-database" in root_response1.text
    # Now find the signature
    signature = root_response1.text.split("/export-database?s=")[1].split('"')[0]
    root_response = await datasette.client.get(
        "/data/-/export-database?s=" + signature,
        cookies=cookies,
    )
    assert root_response.status_code == 200
    content_disposition = root_response.headers["content-disposition"]
    assert content_disposition.startswith('attachment; filename="data-')
    assert content_disposition.endswith('.db"')
    # Write that out to disk so we can query it
    restored = str(tmpdir / "restored.db")
    with open(restored, "wb") as fp:
        for b in root_response.iter_bytes():
            fp.write(b)
    conn = sqlite3.connect(restored)
    assert conn.execute("select count(*) from big").fetchone()[0] == 1001


@pytest.mark.asyncio
async def test_no_space(db_path, tmpdir, monkeypatch):
    monkeypatch.setattr(shutil, "disk_usage", lambda x: (100, 50, 20))
    datasette = Datasette([db_path])
    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    root_response1 = await datasette.client.get("/data", cookies=cookies)
    cookies["ds_csrftoken"] = root_response1.cookies["ds_csrftoken"]
    assert "/export-database" in root_response1.text
    # Now find the signature
    signature = root_response1.text.split("/export-database?s=")[1].split('"')[0]
    root_response = await datasette.client.get(
        "/data/-/export-database?s=" + signature,
        cookies=cookies,
    )
    assert root_response.status_code == 403
    assert root_response.text == "Not enough space in /tmp to export this database"


@pytest.mark.asyncio
async def test_bad_csrftoken(db_path):
    datasette = Datasette([db_path])
    cookies1 = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    cookies2 = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    root_response1 = await datasette.client.get("/data", cookies=cookies1)
    cookies1["ds_csrftoken"] = root_response1.cookies["ds_csrftoken"]
    root_response2 = await datasette.client.get("/data", cookies=cookies2)
    cookies2["ds_csrftoken"] = root_response2.cookies["ds_csrftoken"]
    signature1 = root_response1.text.split("/export-database?s=")[1].split('"')[0]
    signature2 = root_response1.text.split("/export-database?s=")[1].split('"')[0]
    # Trying to use signature2 to export database for root1 user will break
    response = await datasette.client.get(
        "/data/-/export-database?s=" + signature1,
        cookies=cookies2,
    )
    assert response.status_code == 403
    assert response.text == "Signature csrftoken did not match"
    # But signature1 works for root1 user
    good_response = await datasette.client.get(
        "/data/-/export-database?s=" + signature1,
        cookies=cookies1,
    )
    assert good_response.status_code == 200
