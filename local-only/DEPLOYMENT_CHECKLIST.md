# Deployment checklist

## 1. Push to GitHub
Run:
```bash
git push -u origin main
```

## 2. Create a Supabase project
- Go to https://supabase.com
- Create a new project
- Copy the Postgres connection string

## 3. Add the database secret
In Streamlit Cloud, add this secret:
```toml
DATABASE_URL = "postgres://..."
```

## 4. Deploy the app
- Open Streamlit Community Cloud
- Connect the GitHub repo
- Choose the repo and branch
- Set the main file to app.py
- Deploy

## 5. Run the migration
Once the app is deployed, run the migration script with the same DATABASE_URL secret configured.
