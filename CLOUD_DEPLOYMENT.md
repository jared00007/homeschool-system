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

### ⚠️ Use Supabase's Pooler connection string, not the Direct connection

Supabase gives you two connection strings in the project dashboard (Settings
→ Database → Connection string):

- **Direct connection** (`db.<project-ref>.supabase.co`, port 5432) — this
  host is **IPv6-only**. Most hosted platforms (including Streamlit
  Community Cloud) don't have outbound IPv6, so this connection will fail
  to resolve/connect from there. It works fine from a machine with IPv6.
- **Session pooler** or **Transaction pooler** (host like
  `aws-0-<region>.pooler.supabase.com`, username `postgres.<project-ref>`,
  port `5432` or `6543`) — IPv4-compatible, works from any host. **Use one
  of these for `DATABASE_URL` when deploying to Streamlit Cloud or any
  other hosted platform.**

If the app fails to connect, it now raises a clear error (instead of
silently falling back to local SQLite) telling you the host/port it tried
and the underlying error — check the Streamlit Cloud app logs ("Manage app"
→ logs) for that message if data isn't loading.

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
