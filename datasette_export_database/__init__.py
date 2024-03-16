import asyncio
from datetime import datetime, timezone
from datasette import hookimpl, Response
from datasette.utils.asgi import asgi_send_file
import itsdangerous
from jinja2.filters import do_filesizeformat
import pathlib
import secrets
import shutil
import tempfile
import time

TMP_PREFIX = "datasette-export-database-"
tmp_dir = tempfile.gettempdir()


@hookimpl
def register_permissions(datasette):
    # Not present in <1.0 so import it here
    from datasette.permissions import Permission

    return [
        Permission(
            name="export-database",
            abbr=None,
            description="Export snapshots of the database",
            takes_database=True,
            takes_resource=False,
            default=False,
        )
    ]


@hookimpl
def register_routes():
    return [
        ("^/(?P<database>[^/]+)/-/export-database", export_database),
    ]


@hookimpl
def permission_allowed(action, actor):
    if action == "export-database" and actor and actor.get("id") == "root":
        return True


@hookimpl
def startup(datasette):
    datasette._datasette_export_database_cleanup_task = asyncio.create_task(
        cleanup_task()
    )


def cleanup_task_sync():
    path = pathlib.Path(tmp_dir)
    for file in path.glob(TMP_PREFIX + "*"):
        # We use modified not created time because our tests can
        # fake the modified time but harder to create created time
        age_in_seconds = time.time() - file.stat().st_mtime
        if age_in_seconds > 3600:
            file.unlink()


async def cleanup_task():
    # Once an hour scans /tmp for TMP_PREFIX files that were created more than an hour ago
    while True:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, cleanup_task_sync)
        await asyncio.sleep(60 * 60)


@hookimpl
async def export_database(datasette, request, send):
    database = request.url_vars["database"]
    db = datasette.get_database(database)
    db_path = db.path
    if db_path is None:
        # Must be _internal or an in-memory database
        return Response.text(
            "Database cannot be exported, it does not exist on disk", status=403
        )

    # Check signature
    signature = request.args.get("s") or ""
    try:
        unsigned = datasette.unsign(signature, "export-database")
    except itsdangerous.exc.BadSignature:
        return Response.text("Bad signature", status=403)
    # csrftoken should match
    if not secrets.compare_digest(
        request.cookies.get("ds_csrftoken") or "", unsigned["csrf"]
    ):
        return Response.text("Signature csrftoken did not match", status=403)

    # Is there enough space in /tmp ?
    db_size_bytes = pathlib.Path(db_path).stat().st_size
    free_tmp_bytes = shutil.disk_usage(tmp_dir)[2]
    if free_tmp_bytes < db_size_bytes:
        return Response.text(
            "Not enough space in {} to export this database".format(tmp_dir), status=403
        )

    # Generate a unique filename for the new SQLite database in the /tmp directory
    with tempfile.NamedTemporaryFile(
        prefix="{}{}".format(
            TMP_PREFIX,
            database,
        ),
        suffix=".db",
        delete=False,
        dir=tmp_dir,
    ) as tmp_file:
        new_db_path = tmp_file.name

    # Create the Python command to execute in a subprocess
    command = f"python -c \"import sqlite3; conn = sqlite3.connect('{db_path}'); conn.execute('VACUUM INTO \\\"{new_db_path}\\\"'); conn.close()\""

    # Run the command in a subprocess using asyncio
    proc = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )

    # Wait for the subprocess to complete
    stdout, stderr = await proc.communicate()

    # Check if the subprocess completed successfully
    if proc.returncode == 0:
        await asgi_send_file(
            send,
            new_db_path,
            filename="{}-{}.db".format(
                database, datetime.now(timezone.utc).strftime("%Y-%m-%d-%H-%M")
            ),
            content_type="application/octet-stream",
            chunk_size=4096,
        )
        # Now delete the temp file
        pathlib.Path(new_db_path).unlink()
    else:
        # Handle any errors that occurred during the subprocess execution
        error_message = stderr.decode().strip()
        return Response.text(error_message, status=500)


@hookimpl
def database_actions(datasette, actor, database, request):
    async def inner():
        if not await datasette.permission_allowed(
            actor,
            "export-database",
            resource=database,
            default=False,
        ):
            return
        db = datasette.get_database(database)
        if db.path is None:
            return
        # Signing with the csrftoken because even anonymous users will have one
        href = (
            datasette.urls.database(database)
            + "/-/export-database?s="
            + datasette.sign({"csrf": request.scope["csrftoken"]()}, "export-database")
        )
        return [
            {
                "href": href,
                "label": "Export this database",
                "description": "Create and download a snapshot of this SQLite database ({})".format(
                    do_filesizeformat(pathlib.Path(db.path).stat().st_size)
                ),
            }
        ]

    return inner
