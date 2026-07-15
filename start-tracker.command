#!/bin/bash
# Launcher for the Homeschool Tracker app.
# Double-click this file to start the tracker in your browser.

cd ~/Desktop/homeschool-system/tracker || {
  echo "Could not find ~/Desktop/homeschool-system/tracker"
  echo "If you moved the folder, edit the path on line 5 of this file."
  read -p "Press Enter to close..."
  exit 1
}

# Create the virtual environment on first run if it doesn't exist yet
# (dependencies come from the repo-root requirements.txt — the single
# source of truth used both locally and by the cloud deployment)
if [ ! -d "venv" ]; then
  echo "First-time setup: creating environment and installing dependencies..."
  python3 -m venv venv
  source venv/bin/activate
  pip install -r ../requirements.txt
else
  source venv/bin/activate
fi

streamlit run app.py
