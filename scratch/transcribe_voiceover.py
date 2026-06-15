import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment.")
        exit(1)

    audio_path = "outputs/reel_system_prompt/assets/voiceover.mp3"
    if not os.path.exists(audio_path):
        print(f"Error: Voiceover file not found at {audio_path}")
        exit(1)

    print("Initializing GenAI client...")
    client = genai.Client(api_key=api_key)

    print(f"Uploading audio file {audio_path} to Gemini...")
    audio_file = client.files.upload(file=audio_path)
    print(f"Uploaded successfully. File URI: {audio_file.uri}")

    prompt = (
        "You are an expert video editor. Analyze this audio file and transcribe the spoken words. "
        "For each sentence or logical thought block, provide the start and end timestamps in seconds. "
        "Format the output strictly as a JSON list of objects, like this:\n"
        "[\n"
        "  {\n"
        "    \"text\": \"Sentence text here\",\n"
        "    \"start\": 0.0,\n"
        "    \"end\": 4.5\n"
        "  }\n"
        "]\n"
        "Do not include any markdown formatting blocks or explanations."
    )

    print("Querying Gemini for speech transcription and timing analysis...")
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=[audio_file, prompt]
        )
        print("\n=== Gemini Response ===")
        print(response.text)
        print("=======================\n")
        
        # Save response to a json file
        output_path = "outputs/reel_system_prompt/assets/audio_timestamps.json"
        with open(output_path, "w") as f:
            f.write(response.text)
        print(f"Saved timestamps to {output_path}")

    except Exception as e:
        print(f"Error querying Gemini API: {e}")
    finally:
        # Clean up the file from Gemini
        print("Cleaning up file from Gemini cloud...")
        client.files.delete(name=audio_file.name)
        print("Cleanup completed.")

if __name__ == "__main__":
    main()
