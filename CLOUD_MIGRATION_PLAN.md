# Simple cloud migration plan for Homeschool One-Stop

## Goal
Make the app available from anywhere, while keeping the product simple and low-risk.

## What is changing
Right now the app is local-only:
- the Streamlit app runs on your Mac
- data lives in a local SQLite database
- uploads are stored locally

For the first cloud version, we will keep the same app experience and move only the storage and hosting layer.

## Recommended simple approach
Use:
- GitHub for the code
- Supabase for the database
- Supabase Storage for uploads
- Streamlit Community Cloud (or Render) for hosting the app

This is the easiest path for a first migration because it is beginner-friendly and does not require building a full custom server.

## Phase 1 — keep it simple
Start with the core app only:
1. Put the project in GitHub.
2. Create a Supabase project.
3. Replace the local SQLite database with a cloud PostgreSQL database.
4. Keep the UI the same.
5. Test the app with a small amount of real data.

## Phase 2 — move files and uploads
1. Move photo uploads to Supabase Storage.
2. Keep the app working with cloud-stored files.
3. Do not add extra features yet.

## Phase 3 — make it usable from anywhere
1. Deploy the app to Streamlit Community Cloud.
2. Set the required environment variables.
3. Confirm that parent mode and student mode both work in the cloud.
4. Make sure backups are still easy.

## What to avoid for now
To keep this simple, do not try to do all of these at once:
- a full custom server
- a complicated auth system
- fancy multi-user roles
- rebuilding the whole app from scratch

## Suggested first milestone
The first milestone should be:
- app runs in the cloud
- hours, grades, and assessments save to cloud storage
- no photos yet if that feels too much

## Practical rollout order
1. GitHub repo
2. Supabase database
3. app switched to cloud DB
4. deploy to Streamlit Cloud
5. add uploads later if needed

## Recommended decision
If you want the least stressful version, choose:
- Streamlit Community Cloud for hosting
- Supabase for database and file storage

That gives you a real cloud version without needing to learn too much at once.

## Next step
The next step should be a very small technical pass:
- swap the local database connection to a cloud database connection
- keep the rest of the app unchanged

If you want, I can help you do that next and keep it very simple.
