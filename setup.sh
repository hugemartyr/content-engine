#!/bin/bash
set -e

echo "=== Scaffolding Content Intelligence Engine Directory Structure ==="
mkdir -p agents/trend_agent agents/scoring_agent agents/kg_agent agents/idea_agent agents/script_agent agents/scene_agent agents/retrieval_agent agents/ranking_agent agents/timeline_agent
mkdir -p core/graph core/prompts core/schemas core/settings core/logging core/utils
mkdir -p services/github services/reddit services/youtube services/newsletters services/stock services/screenshots
mkdir -p knowledge_graph/entities knowledge_graph/relations knowledge_graph/enrichers
mkdir -p data/github data/reddit data/youtube data/newsletters
mkdir -p outputs/trends outputs/ideas outputs/scripts outputs/assets outputs/timelines
mkdir -p tests api docs

echo "=== Initializing Configuration ==="
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example (please edit with your GEMINI_API_KEY)"
else
  echo ".env already exists, skipping copy"
fi

echo "=== Setting Up Virtual Environment & Dependencies ==="
python3 -m venv venv
source venv/bin/activate

echo "Installing pip requirements..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Installing Playwright browsers..."
playwright install chromium

echo "=== Generating Mock BGM Assets ==="
# Write small mock MP3 files
echo -n "MOCK_AUDIO_DATA_AMBIENT_TECH_MELLOW" > outputs/assets/ambient_tech_mellow.mp3
echo -n "MOCK_AUDIO_DATA_LOFI_STUDY_BEATS" > outputs/assets/lofi_study_beats.mp3
echo -n "MOCK_AUDIO_DATA_TECH_DOCUMENTARY" > outputs/assets/tech_documentary.mp3

echo "=== Scaffold Completed Successfully ==="
echo "To run the application:"
echo "  source venv/bin/activate"
echo "  uvicorn api.app:app --reload"
