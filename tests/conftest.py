from datasette.plugins import pm
import datasette_export_database

if not pm.is_registered(datasette_export_database):
    pm.register(datasette_export_database, name="datasette_export_database")
