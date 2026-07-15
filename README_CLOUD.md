# Cloud deployment quick start

## 1. Create a Supabase project
- Go to https://supabase.com
- Create a new project
- Copy the Postgres connection string

## 2. Set the connection string
In your shell or hosting platform, set one of these:
- DATABASE_URL
- SUPABASE_DB_URL

Example:
```bash
export DATABASE_URL="postgres://user:password@host:5432/dbname"
```

## 3. Install dependencies
```bash
pip install -r requirements.txt
```

## 4. Migrate local data
```bash
python3 tracker/migrate_to_cloud.py
```

## 5. Run the app
```bash
streamlit run app.py
```
