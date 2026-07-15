# Cloud deployment guide

This app can now be deployed in a simple cloud setup.

## Option 1 — easiest path
Use:
- GitHub for the code
- Supabase for the database
- Streamlit Community Cloud for hosting

## Step 1 — create the database
1. Create a Supabase project.
2. Open the project dashboard.
3. Copy the Postgres connection string.

## Step 2 — add the connection string
For local testing, set one of these:
- DATABASE_URL
- SUPABASE_DB_URL

For Streamlit Cloud, add the same value in app secrets as:
- DATABASE_URL = "postgresql://user:password@host:5432/dbname"

For a proper cloud setup, use a managed Postgres service such as Supabase, Neon, or a similar provider. The app will use that connection automatically when the secret is present.

If you want to keep the app working locally too, leave the local SQLite file in place and only set the cloud variable when you are ready to use the hosted database.

## Step 3 — install dependencies
Run from the repo root:

```bash
pip install -r requirements.txt
```

## Step 4 — migrate your local data
Run:

```bash
python3 tracker/migrate_to_cloud.py
```

This copies the current local SQLite data into the cloud database.

This copies the current local SQLite data into the cloud database.

## Step 5 — deploy the app
1. Push the repo to GitHub.
2. Create a Streamlit Cloud app pointing at the repo.
3. Set the same database secret.
4. Deploy.

## Notes
- Local SQLite still works if no cloud database is configured.
- Photos and uploads can be moved later to Supabase Storage if you want to keep everything fully cloud-based.
