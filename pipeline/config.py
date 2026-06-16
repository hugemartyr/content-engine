import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Default prompt for the "System Prompt" Reel
DEFAULT_PROMPT = """
Topic: Most people using AI are making themselves slower - here's why
Format: Voiceover + text overlays + stock footage. No face shown.
Length: 38 - 42 seconds
Platform: Instagram Reels (9:16, 1080×1920px)
Voice: ElevenLabs - Callum, calm, confident, slightly dry. Not hype. Not breathless.
Goal: Maximum saves. People save this to come back and build their system prompt.
CTA in video: None. Zero. The pinned comment handles it.
THE HOOK - WHY THIS SPECIFIC LINE
Hook line (voiceover + on screen simultaneously):
 "Most people using AI are making themselves slower."

On screen treatment for the hook:
 — Black screen. White text only. Large. Bold. Centered.
 — Text appears word by word in sync with voiceover -not all at once.
 — "Most people" appears → 0.2 second pause → "using AI" → 0.2 second pause → "are making themselves slower" lands all at once.
 — No music at this exact moment. Silence makes the statement land harder.
 — Music fades in at second 1.8 after the hook has landed.
FULL SCRIPT - WORD FOR WORD
0:00–0:03 — Most people using AI... are making themselves slower.
0:03–0:06 — They type a vague prompt. Get a mediocre answer. Edit it for twenty minutes. And call that productivity.
0:06–0:09 — Here is the actual problem.
0:09–0:15 — ChatGPT, Claude, Gemini — none of them know anything about you. Your job. Your writing style. What you actually need.
0:15–0:17 — So every single conversation starts from zero.
0:17–0:22 — The people getting real output from AI? They have built what is called a system prompt. A permanent set of instructions the AI reads before you type anything.
0:22–0:28 — Your role. Your tone. What to avoid. What format you want answers in. Your writing style. All of it. Written once.
0:28–0:31 — I built mine six months ago. I have not edited a single AI output since.
0:31–0:34 — Most people never build one.
0:34–0:40 — Which means they do the same setup work. Every. Single. Session. That is not AI saving you time. That is AI costing you time.
0:40–0:42 — Build the prompt once.
"""
