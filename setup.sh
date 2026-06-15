#!/bin/bash
set -e

echo "=== Initializing Configuration ==="
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
else
  echo ".env already exists, skipping copy"
fi

echo "=== Setting Up Virtual Environment & Dependencies ==="
python3 -m venv venv
source venv/bin/activate

echo "Installing pip requirements..."
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Setup Completed Successfully ==="
echo "To run the pipeline:"
echo "  source venv/bin/activate"
echo "  python generate_viral_reel.py --prompt \"Your prompt details here\""
