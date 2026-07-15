# Cloud migration guide — technical terms

## Objective
Migrate the existing Streamlit-based homeschool application from a local SQLite-backed deployment to a cloud-hosted architecture using a managed PostgreSQL service and a cloud application host.

## Current architecture
The application currently runs as a local Streamlit app with data persisted in a SQLite database file and uploaded files stored on disk. The implementation is centered around a single Python entrypoint in tracker/app.py and a local SQLite connection layer.

## Migration approach
The migration is implemented in three layers:

1. Database abstraction
   - Introduced a small compatibility layer in tracker/db_backend.py.
   - This layer allows the application to connect to either SQLite or a PostgreSQL-compatible service using DATABASE_URL or SUPABASE_DB_URL.

2. Data migration tooling
   - Added tracker/migrate_to_cloud.py.
   - This script reads the existing SQLite database and inserts rows into a remote PostgreSQL database.

3. Deployment readiness
   - Added an app-level entrypoint in app.py for hosting platforms that expect the app root to contain a runnable entry file.
   - Added deployment guidance in CLOUD_DEPLOYMENT.md.

## Why this design
The goal was to minimize disruption to the product while introducing a path to cloud hosting. Rather than re-architecting the entire application, the change isolates the persistence layer and keeps the rest of the Streamlit UI intact.

## Cloud stack recommendation
The recommended minimal stack is:
- GitHub: source control and deployment source
- Supabase: managed PostgreSQL database and optional file storage
- Streamlit Community Cloud: hosting for the app

## Deployment flow
1. Provision a Supabase project and obtain the Postgres connection string.
2. Configure the environment variable DATABASE_URL or SUPABASE_DB_URL.
3. Run the migration script to copy data from the local SQLite database into the remote database.
4. Connect the GitHub repository to Streamlit Cloud.
5. Deploy the app and verify the cloud-backed environment.

## Notes
- Local SQLite remains functional when no cloud database is configured.
- Upload handling can be extended later to Supabase Storage if full cloud-native file storage is desired.
