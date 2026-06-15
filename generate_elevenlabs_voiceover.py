import os
import httpx
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
load_dotenv()

def main():
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("Error: ELEVENLABS_API_KEY not found in environment or .env file.")
        exit(1)

    # Voice ID for Callum
    voice_id = "N2lVS1w4EtoT3dr4eOWO"
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }

    # Punctuation controls the pauses (e.g. ellipses, separate sentences)
    payload = {
        "text": (
            "Most people using AI... are making themselves slower. "
            "They type a vague prompt. Get a mediocre answer. Edit it for twenty minutes. And call that productivity. "
            "Here is the actual problem. "
            "ChatGPT, Claude, Gemini — none of them know anything about you. Your job. Your writing style. What you actually need. "
            "So every single conversation starts from zero. "
            "The people getting real output from AI? They have built what is called a system prompt. A permanent set of instructions the AI reads before you type anything. "
            "Your role. Your tone. What to avoid. What format you want answers in. Your writing style. All of it. Written once. "
            "I built mine six months ago. I have not edited a single AI output since. "
            "Most people never build one. Which means they do the same setup work. Every. Single. Session. "
            "That is not AI saving you time. That is AI costing you time. "
            "Build the prompt once."
        ),
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.75,
            "similarity_boost": 0.80,
            "style": 0.20,
            "speed": 1.15
        }
    }

    print("Synthesizing voiceover with ElevenLabs (Callum)...")
    try:
        response = httpx.post(url, json=payload, headers=headers, timeout=90.0)
    except Exception as e:
        print(f"Network error calling ElevenLabs API: {e}")
        exit(1)

    if response.status_code == 200:
        output_dir = Path("outputs/reel_system_prompt/assets")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "voiceover.mp3"
        with open(output_path, "wb") as f:
            f.write(response.content)
        print(f"Voiceover successfully saved to {output_path}")
    else:
        print(f"Error: ElevenLabs API returned status {response.status_code}")
        print(response.text)
        exit(1)

if __name__ == "__main__":
    main()
