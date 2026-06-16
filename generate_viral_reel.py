import sys
import argparse
import asyncio
from pathlib import Path

# Add project root to sys.path to ensure 'pipeline' module can be imported
sys.path.append(str(Path(__file__).resolve().parent))

try:
    from pipeline.config import DEFAULT_PROMPT
    from pipeline import run_pipeline
except ImportError as e:
    print("Error: Could not import pipeline components.")
    print(e)
    sys.exit(1)

async def main():
    parser = argparse.ArgumentParser(description="Unified LLM-driven Video Reel Pipeline")
    parser.add_argument("--prompt", type=str, help="Textual prompt describing the Reel idea, script, and visual layout.")
    parser.add_argument("--prompt-file", type=str, help="Path to a text file containing the prompt.")
    parser.add_argument("--cleanup", action="store_true", default=True, help="Clean up temporary files after rendering.")
    parser.add_argument("--no-cleanup", action="store_false", dest="cleanup", help="Keep temporary files after rendering.")
    parser.add_argument("--force", action="store_true", help="Force a fresh LLM call, ignoring cached storyboard.")
    args = parser.parse_args()
    
    # 1. Determine Prompt
    prompt_text = DEFAULT_PROMPT
    if args.prompt:
        prompt_text = args.prompt
    elif args.prompt_file:
        prompt_path = Path(args.prompt_file)
        if prompt_path.exists():
            prompt_text = prompt_path.read_text()
        else:
            print(f"Error: Prompt file not found at {args.prompt_file}")
            sys.exit(1)
            
    # Run the pipeline orchestrator
    await run_pipeline(prompt_text, force=args.force, cleanup=args.cleanup)

if __name__ == "__main__":
    asyncio.run(main())
