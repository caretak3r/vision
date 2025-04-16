import os
import glob
import hashlib
import base64
from PIL import Image
import google.generativeai as genai
from pathlib import Path
import io

# --- Configuration ---
# Configure the Google AI API key (Ideally load from GitHub Secrets)
# Example: genai.configure(api_key=os.environ["GEMINI_API_KEY"])
# Make sure to set the GEMINI_API_KEY secret in your GitHub repo settings
try:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    print("Google AI API Key configured.")
except KeyError:
    print("Error: GEMINI_API_KEY environment variable not set.")
    print("Please configure the GEMINI_API_KEY secret in your GitHub repository settings.")
    exit(1) # Exit if the key is not configured

# Configure the generative model
# Use a model that supports image input, like 'gemini-pro-vision' or the latest vision model
model = genai.GenerativeModel('gemini-2.0-flash') # Or use 'gemini-1.5-flash', 'gemini-1.5-pro' etc.
print(f"Using Generative Model: {model.model_name}")

# Directory to search for images (root of the repo in a GitHub Action)
search_dir = '.'
# Supported image extensions
image_extensions = ('*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.webp')
# Output README file
readme_file = 'README.md'

# --- Helper Functions ---

def calculate_hash(image_path):
    """Calculates the SHA-256 hash of an image file."""
    hasher = hashlib.sha256()
    with open(image_path, 'rb') as img_file:
        while chunk := img_file.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def get_image_metadata(image_path):
    """Extracts basic metadata from an image file."""
    try:
        with Image.open(image_path) as img:
            return {
                "dimensions": f"{img.width}x{img.height}",
                "format": img.format,
                "mode": img.mode,
                "size_kb": f"{os.path.getsize(image_path) / 1024:.2f} KB"
            }
    except Exception as e:
        print(f"Error getting metadata for {image_path}: {e}")
        return {
            "dimensions": "N/A",
            "format": "N/A",
            "mode": "N/A",
            "size_kb": f"{os.path.getsize(image_path) / 1024:.2f} KB" # Still provide size if possible
        }

def generate_tags_and_description(image_path):
    """Generates tags and a brief description using Google AI."""
    print(f"Generating tags for: {image_path}")
    try:
        img_pil = Image.open(image_path)

        # Prepare the prompt for the model
        prompt = """
        Analyze this image and provide:
        1. A list of 5-10 relevant single-word tags (comma-separated).
        2. A concise one-sentence description of the image content.

        Format the output exactly like this:
        Tags: tag1,tag2,tag3
        Description: A brief description here.
        """

        # Send the image and prompt to the model
        # Note: Ensure the model you chose ('gemini-pro-vision', 'gemini-1.5-flash', etc.)
        # is suitable and handles images correctly. Refer to google-genai documentation.
        response = model.generate_content([prompt, img_pil], stream=False)
        response.resolve() # Ensure the response is fully generated

        # --- Parsing the response ---
        # This parsing assumes the model follows the requested format.
        # Add robust error handling and retries as needed.
        tags = "Error generating tags"
        description = "Error generating description"

        if response.text:
            lines = response.text.strip().split('\n')
            for line in lines:
                if line.startswith("Tags:"):
                    tags = line.replace("Tags:", "").strip()
                elif line.startswith("Description:"):
                    description = line.replace("Description:", "").strip()
        else:
             print(f"Warning: No text response from AI for {image_path}.")
             # You might want to inspect response.candidates or response.prompt_feedback for issues

        return tags, description

    except Exception as e:
        print(f"Error generating tags/description for {image_path}: {e}")
        # Consider adding retry logic here
        return "Error", f"Failed to process with AI: {e}"

def find_image_files(directory, extensions):
    """Finds all image files with given extensions in a directory."""
    files_found = []
    for ext in extensions:
        # Use recursive glob to find files in subdirectories as well
        files_found.extend(glob.glob(os.path.join(directory, '**', ext), recursive=True))
    # Filter out files within .git directory or other unwanted paths
    files_found = [f for f in files_found if '.git' not in Path(f).parts]
    # Convert to relative paths for cleaner output in README
    files_found = [os.path.relpath(f, directory) for f in files_found]
    return files_found

# --- Main Script Logic ---

print("Starting image indexing process...")
image_files = find_image_files(search_dir, image_extensions)
print(f"Found {len(image_files)} image files.")

image_data = []

for img_path in image_files:
    print(f"\nProcessing: {img_path}")
    # Ensure the path is treated correctly relative to the script execution dir
    full_img_path = os.path.join(search_dir, img_path)

    if not os.path.exists(full_img_path):
        print(f"Warning: File not found at {full_img_path}. Skipping.")
        continue

    file_hash = calculate_hash(full_img_path)
    metadata = get_image_metadata(full_img_path)
    tags, description = generate_tags_and_description(full_img_path)

    image_data.append({
        "path": img_path.replace('\\', '/'), # Ensure forward slashes for markdown/HTML
        "hash": file_hash,
        "metadata": metadata,
        "tags": tags,
        "description": description
    })
    print(f"Finished processing: {img_path}")

print("\nGenerating README.md...")

# --- Generate README.md ---
with open(readme_file, 'w', encoding='utf-8') as f:
    f.write("# Image Index\n\n")
    f.write("This README automatically indexes images found in the repository.\n\n")
    f.write("| Image | Filename | Description | Tags | Metadata | Hash |\n")
    f.write("|---|---|---|---|---|---|\n")

    # Sort data for consistent README generation (optional)
    image_data.sort(key=lambda x: x['path'])

    for data in image_data:
        # Create a relative path suitable for markdown image embedding
        # Assumes README.md is at the root. Adjust if needed.
        md_image_path = data['path']

        # Prepare metadata string
        meta_str = f"Dimensions: {data['metadata']['dimensions']} <br> Format: {data['metadata']['format']} <br> Mode: {data['metadata']['mode']} <br> Size: {data['metadata']['size_kb']}"

        # Write table row
        f.write(f"| ![{data['path']}]({md_image_path}?raw=true) | `{data['path']}` | {data['description']} | `{data['tags']}` | {meta_str} | `{data['hash'][:12]}...` |\n") # Shorten hash for display

print(f"README.md generated successfully at {readme_file}")
print("Image indexing complete.")
