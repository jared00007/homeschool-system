#!/bin/bash
# Launcher for the Homeschool Tracker app.
# Double-click this file to start the tracker. It runs entirely on this
# Mac (data stays in a local SQLite file, nothing goes to the internet)
# and is also reachable from other devices on the same home network —
# e.g. Landon's laptop or phone, over WiFi — using the network address
# printed below once the server starts.

cd ~/Desktop/homeschool-system/tracker || {
  echo "Could not find ~/Desktop/homeschool-system/tracker"
  echo "If you moved the folder, edit the path on line 5 of this file."
  read -p "Press Enter to close..."
  exit 1
}

# Create the virtual environment on first run if it doesn't exist yet
if [ ! -d "venv" ]; then
  echo "First-time setup: creating environment and installing dependencies..."
  python3 -m venv venv
  source venv/bin/activate
  pip install -r ../requirements.txt
else
  source venv/bin/activate
fi

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)

echo ""
echo "======================================================================"
echo "  Starting the Homeschool Tracker..."
echo ""
echo "  On this Mac, it will open at:      http://localhost:8501"
if [ -n "$LAN_IP" ]; then
  echo "  From another device on the same"
  echo "  WiFi network (e.g. Landon's       http://$LAN_IP:8501"
  echo "  laptop or phone), open:"
else
  echo "  Could not detect this Mac's network address automatically."
  echo "  Find it under System Settings > WiFi > Details > IP Address,"
  echo "  then open http://<that address>:8501 on the other device."
fi
echo ""
echo "  The first time another device connects, macOS may ask whether"
echo "  to allow incoming network connections — click Allow."
echo "======================================================================"
echo ""

streamlit run app.py --server.address 0.0.0.0
