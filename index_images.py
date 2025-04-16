import os
import glob
import hashlib
import base64
from PIL import Image
import google.generativeai as genai
from pathlib import Path
import io
import time
import random
import json

# --- Configuration ---
CACHE_FILE = 'image_cache.json'
MAX_RETRIES = 5  # Max attempts for API calls
INITIAL_BACKOFF_SECS = 2  # Initial wait time in seconds for backoff

# Configure the Google AI API key (Load from GitHub Secrets)
try:
    # Using the environment variable name provided by the user
    api_key = os.environ["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    print("Google AI API Key configured.")
except KeyError:
    print("Error: GEMINI_API_KEY environment variable not set.")
    print("Please configure the GEMINI_API_KEY secret in your GitHub repository settings.")
    exit(1) # Exit if the key is not configured

# Configure the generative model
# Use a model that supports image input.
# Using 'gemini-1.5-flash-latest' as 'gemini-2.0-flash' might not be valid.
# Adjust to 'gemini-1.5-pro-latest' or other models if needed.
try:
    model = genai.GenerativeModel('gemini-2.0-flash')
    print(f"Using Generative Model: {model.model_name}")
except Exception as e:
    print(f"Error configuring Generative Model: {e}")
    print("Please ensure the model name is correct and the API key is valid.")
    exit(1)

# Directory to search for images (root of the repo in a GitHub Action)
search_dir = '.'
# Supported image extensions
image_extensions = ('*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.webp')
# Output README file
readme_file = 'README.md'

# --- Helper Functions ---

def load_cache(cache_file_path):
    """Loads the image processing cache from a JSON file."""
    if os.path.exists(cache_file_path):
        try:
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                # Check if file is empty
                content = f.read()
                if not content:
                    print(f"Cache file '{cache_file_path}' is empty. Starting with an empty cache.")
                    return {}
                # Reset file pointer and load JSON
                f.seek(0)
                cache = json.load(f)
                print(f"Loaded cache with {len(cache)} entries from {cache_file_path}")
                return cache
        except json.JSONDecodeError:
            print(f"Warning: Cache file '{cache_file_path}' contains invalid JSON. Starting with an empty cache.")
            return {}
        except Exception as e:
            print(f"Warning: Could not load cache file '{cache_file_path}'. Error: {e}. Starting with an empty cache.")
            return {}
    else:
        print(f"Cache file '{cache_file_path}' not found. Starting with an empty cache.")
        return {}

def save_cache(cache_data, cache_file_path):
    """Saves the image processing cache to a JSON file."""
    try:
        with open(cache_file_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=4)
        print(f"Saved cache with {len(cache_data)} entries to {cache_file_path}")
    except Exception as e:
        print(f"Error saving cache to {cache_file_path}: {e}")


def calculate_hash(image_path):
    """Calculates the SHA-256 hash of an image file."""
    hasher = hashlib.sha256()
    try:
        with open(image_path, 'rb') as img_file:
            while chunk := img_file.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except FileNotFoundError:
        print(f"Error: File not found during hash calculation: {image_path}")
        return None
    except Exception as e:
        print(f"Error calculating hash for {image_path}: {e}")
        return None


def get_image_metadata(image_path):
    """Extracts basic metadata from an image file."""
    try:
        with Image.open(image_path) as img:
            # Ensure image data is loaded to catch potential errors early
            img.load()
            # Get file size safely
            try:
                size_bytes = os.path.getsize(image_path)
                size_kb = f"{size_bytes / 1024:.2f} KB"
            except FileNotFoundError:
                 size_kb = "N/A (File not found)"
            except Exception as size_e:
                 size_kb = f"N/A (Error: {size_e})"

            return {
                "dimensions": f"{img.width}x{img.height}",
                "format": img.format or "N/A",
                "mode": img.mode or "N/A",
                "size_kb": size_kb
            }
    except FileNotFoundError:
         print(f"Error: File not found when getting metadata: {image_path}")
         # Try to get size anyway if possible, otherwise return N/A for all
         try:
             size_bytes = os.path.getsize(image_path)
             size_kb = f"{size_bytes / 1024:.2f} KB"
         except Exception:
             size_kb = "N/A"
         return { "dimensions": "N/A", "format": "N/A", "mode": "N/A", "size_kb": size_kb }
    except Image.UnidentifiedImageError:
        print(f"Error: Cannot identify image file (possibly corrupt or unsupported format): {image_path}")
        return { "dimensions": "N/A", "format": "Unidentified", "mode": "N/A", "size_kb": "N/A" }
    except Exception as e:
        print(f"Error getting metadata for {image_path}: {e}")
        # Try to get size anyway if possible
        try:
             size_bytes = os.path.getsize(image_path)
             size_kb = f"{size_bytes / 1024:.2f} KB"
        except Exception:
             size_kb = "N/A"
        return { "dimensions": "N/A", "format": "N/A", "mode": "N/A", "size_kb": size_kb }


def generate_tags_and_description(image_path):
    """Generates tags and description using Google AI with backoff."""
    print(f"Attempting to generate tags via API for: {image_path}")
    retries = 0
    while retries < MAX_RETRIES:
        try:
            img_pil = Image.open(image_path)
            # Ensure image data is loaded before sending to API
            img_pil.load()

            prompt = """
            Analyze this image and provide:
            1. A list of 5-10 relevant single-word tags (comma-separated). Use lowercase.
            2. A concise one-sentence description of the image content.

            Format the output exactly like this, with no extra text before or after:
            Tags: tag1,tag2,tag3
            Description: A brief description here.
            """

            # --- API Call ---
            response = model.generate_content([prompt, img_pil], stream=False)
            response.resolve() # Ensure the response is fully generated

            # --- Parsing the response ---
            tags = "Error: Could not parse AI response"
            description = "Error: Could not parse AI response"

            if response.text:
                lines = response.text.strip().split('\n')
                parsed_tags = False
                parsed_desc = False
                for line in lines:
                    if line.lower().startswith("tags:"):
                        tags = line[len("Tags:"):].strip()
                        parsed_tags = True
                    elif line.lower().startswith("description:"):
                        description = line[len("Description:"):].strip()
                        parsed_desc = True
                if not parsed_tags and not parsed_desc:
                     # Handle cases where the model might not follow the format exactly
                     print(f"Warning: AI response for {image_path} did not strictly follow format. Raw response: {response.text[:200]}...")
                     # Try a simple heuristic: assume first line is tags, second is description if available
                     if len(lines) >= 1: tags = lines[0].strip()
                     if len(lines) >= 2: description = lines[1].strip()
                     else: description = "Could not parse description from AI response."


            else:
                 print(f"Warning: No text response from AI for {image_path}.")
                 # Check for safety blocks or other issues
                 try:
                     if response.prompt_feedback.block_reason:
                         reason = response.prompt_feedback.block_reason
                         print(f"Content blocked for {image_path}. Reason: {reason}")
                         return "Blocked", f"Content blocked by API. Reason: {reason}"
                 except (AttributeError, ValueError):
                     # Handle cases where feedback might not be present or structured as expected
                      pass
                 return "Error: No text from AI", "Error: No text response received from AI."

            print(f"Successfully generated tags/description for {image_path}")
            return tags, description # Success

        except Image.UnidentifiedImageError:
            print(f"Error: Cannot identify image file (skipped API call): {image_path}")
            return "Error: Invalid Image", "Cannot identify image file (corrupt or unsupported format)."
        except FileNotFoundError:
            print(f"Error: File not found before API call: {image_path}")
            return "Error: File Not Found", "Image file was not found during processing."
        except Exception as e:
            # Catch potential API errors (like rate limits, server errors, etc.)
            # Ideally, catch specific exceptions from google.api_core.exceptions if known
            # e.g., except google.api_core.exceptions.ResourceExhausted as rate_limit_error:
            retries += 1
            print(f"Error generating tags/description for {image_path}: {e}. Retry {retries}/{MAX_RETRIES}...")

            if retries >= MAX_RETRIES:
                print(f"Failed to generate tags for {image_path} after {MAX_RETRIES} retries.")
                return "Error: Max Retries", f"Failed to process with AI after multiple retries: {e}"

            # Exponential backoff with jitter
            wait_time = INITIAL_BACKOFF_SECS * (2 ** (retries - 1))
            sleep_duration = wait_time + random.uniform(0, wait_time * 0.5) # Add jitter
            print(f"Waiting for {sleep_duration:.2f} seconds before retrying...")
            time.sleep(sleep_duration)

    # Should not be reached if loop logic is correct, but as a fallback
    return "Error: Unknown Failure", "An unexpected error occurred during tag generation."


def find_image_files(directory, extensions):
    """Finds all image files with given extensions in a directory, excluding .git."""
    files_found = []
    print(f"Searching for images in: {os.path.abspath(directory)}")
    for ext in extensions:
        # Use recursive glob to find files in subdirectories
        pattern = os.path.join(directory, '**', ext)
        found = glob.glob(pattern, recursive=True)
        # Filter out files within .git directory or other unwanted paths like the cache file itself
        for f in found:
             path_obj = Path(f)
             # Check if '.git' is in the path parts and if the file is the cache file
             if '.git' not in path_obj.parts and path_obj.name != CACHE_FILE:
                 # Convert to relative path for cleaner output and consistency
                 relative_path = os.path.relpath(f, directory)
                 files_found.append(relative_path)

    # Remove duplicates that might arise from overlapping patterns or symlinks
    files_found = sorted(list(set(files_found)))
    print(f"Found {len(files_found)} unique image files.")
    return files_found

# --- Main Script Logic ---

print("Starting image indexing process...")

# Load existing cache
image_cache = load_cache(CACHE_FILE)
processed_hashes = set(image_cache.keys())
all_image_data = [] # To store data for README generation

# Find all image files in the repository
image_files = find_image_files(search_dir, image_extensions)

# --- Processing Loop ---
newly_processed_count = 0
skipped_count = 0
error_count = 0

for img_rel_path in image_files:
    print("-" * 20)
    print(f"Processing: {img_rel_path}")
    full_img_path = os.path.join(search_dir, img_rel_path)

    if not os.path.exists(full_img_path):
        print(f"Warning: File path resolved to '{full_img_path}' which does not exist. Skipping.")
        error_count += 1
        continue

    # Calculate hash first
    current_hash = calculate_hash(full_img_path)
    if current_hash is None:
        print(f"Could not calculate hash for {img_rel_path}. Skipping.")
        error_count += 1
        continue # Skip if hash calculation failed

    # Get metadata (always get fresh metadata in case file changed)
    metadata = get_image_metadata(full_img_path)

    # Check cache
    if current_hash in image_cache:
        print(f"Cache hit for {img_rel_path} (Hash: {current_hash[:8]}...). Using cached tags/description.")
        cached_data = image_cache[current_hash]
        tags = cached_data.get("tags", "N/A (from cache)")
        description = cached_data.get("description", "N/A (from cache)")
        skipped_count += 1
    else:
        print(f"Cache miss for {img_rel_path} (Hash: {current_hash[:8]}...). Generating tags via API.")
        # Generate tags and description via API only if not in cache
        tags, description = generate_tags_and_description(full_img_path)
        if not tags.startswith("Error:") and not description.startswith("Error:"):
             # Add to cache only if successfully processed
             image_cache[current_hash] = {"tags": tags, "description": description}
             processed_hashes.add(current_hash) # Keep track of processed hashes this run
             newly_processed_count += 1
             print(f"Successfully processed and added to cache: {img_rel_path}")
        else:
             print(f"Skipping caching due to processing errors for: {img_rel_path}")
             error_count += 1


    # Add data for README generation (always add, using cached or new data)
    all_image_data.append({
        "path": img_rel_path.replace('\\', '/'), # Ensure forward slashes
        "hash": current_hash,
        "metadata": metadata,
        "tags": tags,
        "description": description
    })

print("-" * 20)
print(f"\nProcessing Summary:")
print(f"  - Images found: {len(image_files)}")
print(f"  - Newly processed (API calls): {newly_processed_count}")
print(f"  - Skipped (used cache): {skipped_count}")
print(f"  - Errors/Skipped: {error_count}")


# --- Generate README.md ---
print("\nGenerating README.md...")
try:
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write("# Image Index\n\n")
        f.write(f"This README automatically indexes images found in the repository. Last updated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n")
        f.write("| Image | Filename | Description | Tags | Metadata | Hash |\n")
        f.write("|---|---|---|---|---|---|\n")

        # Sort data for consistent README generation
        all_image_data.sort(key=lambda x: x['path'])

        for data in all_image_data:
            # Create a relative path suitable for markdown image embedding
            # Assumes README.md is at the root. Adjust if needed.
            # Use raw=true for GitHub to render the image directly
            md_image_path = data['path'] + "?raw=true"
            img_tag = f"![{os.path.basename(data['path'])}]({md_image_path})"

            # Prepare metadata string more robustly
            meta_items = [
                f"Dims: {data['metadata'].get('dimensions', 'N/A')}",
                f"Format: {data['metadata'].get('format', 'N/A')}",
                # f"Mode: {data['metadata'].get('mode', 'N/A')}", # Mode might be less useful
                f"Size: {data['metadata'].get('size_kb', 'N/A')}"
            ]
            meta_str = " <br> ".join(item for item in meta_items if 'N/A' not in item)
            if not meta_str: meta_str = "N/A" # Handle case where all metadata failed


            # Escape potential pipe characters in description or tags to avoid breaking table
            safe_description = data['description'].replace('|', '\\|') if data.get('description') else 'N/A'
            safe_tags = data['tags'].replace('|', '\\|') if data.get('tags') else 'N/A'

            # Write table row
            f.write(f"| {img_tag} | `{data['path']}` | {safe_description} | `{safe_tags}` | {meta_str} | `{data['hash'][:12]}...` |\n")

    print(f"README.md generated successfully at {readme_file}")

except Exception as e:
    print(f"Error generating README.md: {e}")

# --- Save Cache ---
# Clean up cache: Remove entries for hashes that no longer correspond to found image files
# This handles deleted images.
# Note: This doesn't handle renamed images perfectly (they'll be treated as new).
# A more complex system would be needed to track renames.
hashes_in_repo = {item['hash'] for item in all_image_data if item['hash']}
hashes_to_keep = set(image_cache.keys()) & hashes_in_repo
cleaned_cache = {h: image_cache[h] for h in hashes_to_keep}

if len(cleaned_cache) < len(image_cache):
    print(f"Removed {len(image_cache) - len(cleaned_cache)} stale entries from cache.")

save_cache(cleaned_cache, CACHE_FILE)

print("\nImage indexing complete.")

