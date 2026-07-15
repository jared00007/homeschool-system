# Cloud migration guide — simple terms

## What we are doing
We are moving your homeschool app from being stored only on your Mac to being able to run from the cloud.

## Why
Right now the app works well locally, but it is tied to one computer. Moving it to the cloud makes it easier to access from another device and keeps the data in a safer, more reliable place.

## What changed
We made the app ready for a cloud setup by:
- adding a way for the app to talk to a remote database
- creating a migration script to move the local data into the cloud
- making the app easier to deploy to a hosting service

## In simple words
Think of it like this:
- your Mac is currently the home for the app
- the cloud becomes the new home for the data
- the app still works the same way, but now it can live somewhere more accessible

## What the cloud pieces are
- GitHub: holds the code
- Supabase: stores the database and files
- Streamlit Cloud: runs the app

## What happens next
1. Create a cloud database
2. Connect the app to it
3. Move the current local data over
4. Publish the app online

## What to expect
This is a simple migration, not a full rebuild. The app should keep the same features while moving the storage and hosting to the cloud.
