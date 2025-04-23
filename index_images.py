import os
import glob
import hashlib
# import base64 # No longer explicitly used, can be removed if desired
from PIL import Image
import google.generativeai as genai
from pathlib import Path
# import io # No longer explicitly used, can be removed if desired
import time
import random
import json
import re # Import regular expression module

# --- Configuration ---
CACHE_FILE = 'image_cache.json'
MAX_RETRIES = 5  # Max attempts for API calls
INITIAL_BACKOFF_SECS = 2  # Initial wait time in seconds for backoff

# Configure the Google AI API key (Load from GitHub Secrets)
try:
    api_key = os.environ["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    print("Google AI API Key configured.")
except KeyError:
    print("Error: GEMINI_API_KEY environment variable not set.")
    print("Please configure the GEMINI_API_KEY secret in your GitHub repository settings.")
    exit(1) # Exit if the key is not configured

# Configure the generative model
try:
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
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

def normalize_and_rename(file_rel_path, base_dir):
    """
    Normalizes a filename (lowercase, replaces spaces/special chars)
    and renames the file on the filesystem. Handles collisions.
    Returns the new relative path if renamed, otherwise the original relative path.
    """
    full_original_path = os.path.join(base_dir, file_rel_path)
    directory, filename = os.path.split(file_rel_path)
    base_name, extension = os.path.splitext(filename)

    # Normalize: lowercase, replace spaces with underscores
    normalized_base = base_name.lower().replace(' ', '_')
    # Remove disallowed characters (allow letters, numbers, underscore, hyphen)
    normalized_base = re.sub(r'[^a-z0-9_-]', '', normalized_base)
    # Replace multiple consecutive underscores/hyphens with a single one
    normalized_base = re.sub(r'[_]{2,}', '_', normalized_base)
    normalized_base = re.sub(r'[-]{2,}', '-', normalized_base)
    # Remove leading/trailing underscores/hyphens
    normalized_base = normalized_base.strip('_-')

    # Ensure base_name is not empty after normalization
    if not normalized_base:
        normalized_base = "image" # Default name if everything is stripped

    new_filename = f"{normalized_base}{extension.lower()}" # Ensure extension is lowercase too
    new_rel_path = os.path.join(directory, new_filename)
    full_new_path = os.path.join(base_dir, new_rel_path)

    # Proceed only if the path actually changes
    if full_original_path == full_new_path:
        return file_rel_path # No change needed

    # --- Collision Handling ---
    counter = 1
    temp_new_path = full_new_path
    temp_new_rel_path = new_rel_path
    temp_new_filename = new_filename

    # Check if the target path exists and is not the original file itself
    while os.path.exists(temp_new_path) and temp_new_path != full_original_path:
        print(f"  Collision detected for '{temp_new_filename}'. Trying next suffix.")
        # Construct filename with counter
        temp_new_filename = f"{normalized_base}_{counter}{extension.lower()}"
        temp_new_rel_path = os.path.join(directory, temp_new_filename)
        temp_new_path = os.path.join(base_dir, temp_new_rel_path)
        counter += 1

    # Final paths after collision check
    final_new_path = temp_new_path
    final_new_rel_path = temp_new_rel_path

    # Only rename if the final path is different from the original
    if full_original_path != final_new_path:
        try:
            os.rename(full_original_path, final_new_path)
            print(f"  Renamed: '{file_rel_path}' -> '{final_new_rel_path}'")
            return final_new_rel_path # Return the new relative path
        except OSError as e:
            print(f"  Error renaming '{file_rel_path}' to '{final_new_rel_path}': {e}")
            return file_rel_path # Return original path on error
    else:
        # This case can happen if collision handling resulted back in the original path
        # (e.g. file `image_1.jpg` exists, trying to rename `image.jpg` which normalizes to `image.jpg`,
        # collision makes it `image_1.jpg`, which exists but is the original file path)
        return file_rel_path # No actual rename occurred


def load_cache(cache_file_path):
    """Loads the image processing cache from a JSON file."""
    if os.path.exists(cache_file_path):
        try:
            with open(cache_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content:
                    print(f"Cache file '{cache_file_path}' is empty. Starting with an empty cache.")
                    return {}
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
            img.load()
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
         try: size_bytes = os.path.getsize(image_path); size_kb = f"{size_bytes / 1024:.2f} KB"
         except Exception: size_kb = "N/A"
         return { "dimensions": "N/A", "format": "N/A", "mode": "N/A", "size_kb": size_kb }
    except Image.UnidentifiedImageError:
        print(f"Error: Cannot identify image file (possibly corrupt or unsupported format): {image_path}")
        return { "dimensions": "N/A", "format": "Unidentified", "mode": "N/A", "size_kb": "N/A" }
    except Exception as e:
        print(f"Error getting metadata for {image_path}: {e}")
        try: size_bytes = os.path.getsize(image_path); size_kb = f"{size_bytes / 1024:.2f} KB"
        except Exception: size_kb = "N/A"
        return { "dimensions": "N/A", "format": "N/A", "mode": "N/A", "size_kb": size_kb }


def generate_tags_and_description(image_path):
    """Generates tags and description using Google AI with backoff."""
    print(f"Attempting to generate tags via API for: {image_path}")
    retries = 0
    while retries < MAX_RETRIES:
        try:
            img_pil = Image.open(image_path)
            img_pil.load()

            prompt = """
            Analyze this image and provide:
            1. A list of 5-10 relevant single-word tags (comma-separated). Use lowercase.
            2. A concise one-sentence description of the image content.

            Format the output exactly like this, with no extra text before or after:
            Tags: tag1,tag2,tag3
            Description: A brief description here.
            """

            response = model.generate_content([prompt, img_pil], stream=False)
            response.resolve()

            tags = "Error: Could not parse AI response"
            description = "Error: Could not parse AI response"

            if response.text:
                lines = response.text.strip().split('\n')
                parsed_tags = False; parsed_desc = False
                for line in lines:
                    if line.lower().startswith("tags:"):
                        tags = line[len("Tags:"):].strip(); parsed_tags = True
                    elif line.lower().startswith("description:"):
                        description = line[len("Description:"):].strip(); parsed_desc = True
                if not parsed_tags and not parsed_desc:
                     print(f"Warning: AI response for {image_path} did not strictly follow format. Raw response: {response.text[:200]}...")
                     if len(lines) >= 1: tags = lines[0].strip()
                     if len(lines) >= 2: description = lines[1].strip()
                     else: description = "Could not parse description from AI response."
            else:
                 print(f"Warning: No text response from AI for {image_path}.")
                 try:
                     if response.prompt_feedback.block_reason:
                         reason = response.prompt_feedback.block_reason
                         print(f"Content blocked for {image_path}. Reason: {reason}")
                         return "Blocked", f"Content blocked by API. Reason: {reason}"
                 except (AttributeError, ValueError): pass
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
            retries += 1
            print(f"Error generating tags/description for {image_path}: {e}. Retry {retries}/{MAX_RETRIES}...")
            if retries >= MAX_RETRIES:
                print(f"Failed to generate tags for {image_path} after {MAX_RETRIES} retries.")
                return "Error: Max Retries", f"Failed to process with AI after multiple retries: {e}"
            wait_time = INITIAL_BACKOFF_SECS * (2 ** (retries - 1))
            sleep_duration = wait_time + random.uniform(0, wait_time * 0.5)
            print(f"Waiting for {sleep_duration:.2f} seconds before retrying...")
            time.sleep(sleep_duration)

    return "Error: Unknown Failure", "An unexpected error occurred during tag generation."


def find_image_files(directory, extensions):
    """Finds all image files with given extensions in a directory, excluding .git."""
    files_found = []
    print(f"Searching for images in: {os.path.abspath(directory)}")
    for ext in extensions:
        pattern = os.path.join(directory, '**', ext)
        found = glob.glob(pattern, recursive=True)
        for f in found:
             path_obj = Path(f)
             if '.git' not in path_obj.parts and path_obj.name != CACHE_FILE:
                 relative_path = os.path.relpath(f, directory)
                 files_found.append(relative_path)
    files_found = sorted(list(set(files_found)))
    print(f"Found {len(files_found)} unique image candidate files initially.")
    return files_found

# --- Main Script Logic ---

print("Starting image indexing process...")

# 1. Find all potential image files
initial_image_files = find_image_files(search_dir, image_extensions)

# 2. Normalize filenames and rename files on disk
print("\n--- Normalizing Filenames ---")
normalized_image_files = []
renamed_count = 0
for img_rel_path in initial_image_files:
    print(f"Normalizing: {img_rel_path}")
    new_rel_path = normalize_and_rename(img_rel_path, search_dir)
    if new_rel_path != img_rel_path:
        renamed_count += 1
    normalized_image_files.append(new_rel_path)
print(f"--- Normalization complete. {renamed_count} files potentially renamed. ---")

# Use the list of normalized paths for further processing
image_files_to_process = sorted(list(set(normalized_image_files))) # Ensure uniqueness after potential renames
print(f"Processing {len(image_files_to_process)} images after normalization.")


# 3. Load existing cache
image_cache = load_cache(CACHE_FILE)
processed_hashes = set(image_cache.keys())
all_image_data = [] # To store data for README generation

# 4. Processing Loop (using normalized paths)
print("\n--- Processing Images (Metadata, Cache Check, API Calls) ---")
newly_processed_count = 0
skipped_count = 0
error_count = 0

for img_rel_path in image_files_to_process:
    print("-" * 20)
    print(f"Processing: {img_rel_path}")
    # Use the potentially normalized path
    full_img_path = os.path.join(search_dir, img_rel_path)

    if not os.path.exists(full_img_path):
        print(f"Warning: File path '{full_img_path}' does not exist after normalization/check. Skipping.")
        error_count += 1
        continue

    # Calculate hash first
    current_hash = calculate_hash(full_img_path)
    if current_hash is None:
        print(f"Could not calculate hash for {img_rel_path}. Skipping.")
        error_count += 1
        continue

    # Get metadata (always get fresh metadata)
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
        tags, description = generate_tags_and_description(full_img_path)
        if not tags.startswith("Error:") and not description.startswith("Error:") and tags != "Blocked":
             image_cache[current_hash] = {"tags": tags, "description": description}
             processed_hashes.add(current_hash)
             newly_processed_count += 1
             print(f"Successfully processed and added to cache: {img_rel_path}")
        else:
             print(f"Skipping caching due to processing errors/blocking for: {img_rel_path}")
             error_count += 1

    # Add data for README generation
    all_image_data.append({
        "path": img_rel_path.replace('\\', '/'), # Ensure forward slashes
        "hash": current_hash,
        "metadata": metadata,
        "tags": tags,
        "description": description
    })

print("-" * 20)
print(f"\nProcessing Summary:")
print(f"  - Images found & normalized: {len(image_files_to_process)}")
print(f"  - Newly processed (API calls): {newly_processed_count}")
print(f"  - Skipped (used cache): {skipped_count}")
print(f"  - Errors/Skipped/Blocked: {error_count}")


# 5. Clean cache by removing entries for images that no longer exist in the repository
print("\n--- Cleaning Cache ---")
hashes_in_repo = {item['hash'] for item in all_image_data if item.get('hash')} # Use .get for safety
stale_hashes = set(image_cache.keys()) - hashes_in_repo
if stale_hashes:
    for h in stale_hashes:
        del image_cache[h]
    print(f"Removed {len(stale_hashes)} stale entries from cache (likely deleted images).")
else:
    print("No stale cache entries found.")

# 6. Generate JSON data for frontend
print("\n--- Generating JSON data for frontend ---")
images_data_file = 'images_data.json'
try:
    # Sort images by path
    all_image_data.sort(key=lambda x: x['path'])
    
    # Prepare data in a format suitable for the frontend
    frontend_data = []
    
    # Process all current images first
    for data in all_image_data:
        # Ensure path uses forward slashes
        path = data['path'].replace('\\', '/')
        
        # Convert tags string to array
        tags_array = []
        if isinstance(data.get('tags'), str):
            tags_array = [tag.strip() for tag in data['tags'].split(',') if tag.strip()]
        
        # Format metadata as an object
        metadata = {
            "dimensions": data['metadata'].get('dimensions', 'N/A'),
            "format": data['metadata'].get('format', 'N/A'),
            "size_kb": data['metadata'].get('size_kb', 'N/A')
        }
        
        frontend_data.append({
            "path": path,
            "filename": path,
            "hash": data.get('hash', 'N/A'),
            "description": data.get('description', 'N/A'),
            "tags": tags_array,
            "metadata": metadata
        })
    
    # A set to keep track of hashes we've already processed
    processed_hashes = {item['hash'] for item in frontend_data}
    
    # Check if there are any cached images that aren't in the current repository
    print("Checking cache for additional images...")
    
    for img_hash, img_data in image_cache.items():
        # Skip if we've already processed this hash
        if img_hash in processed_hashes:
            continue
            
        tags = img_data.get('tags', '')
        description = img_data.get('description', 'N/A')
        
        # Convert tags string to array
        tags_array = []
        if isinstance(tags, str):
            tags_array = [tag.strip() for tag in tags.split(',') if tag.strip()]
        
        # Create a placeholder path for cached images that aren't currently in the repo
        # The frontend will handle missing images gracefully
        path = f"cached_image_{img_hash[:8]}"
        
        frontend_data.append({
            "path": path, 
            "filename": path,
            "hash": img_hash,
            "description": description,
            "tags": tags_array,
            "metadata": {
                "dimensions": "N/A",
                "format": "N/A",
                "size_kb": "N/A",
                "cached_only": True
            },
            "cached_only": True
        })
        
        print(f"Added cached image with hash {img_hash[:8]}... to frontend data")
    
    # Write to JSON file
    with open(images_data_file, 'w', encoding='utf-8') as f:
        json.dump(frontend_data, f, indent=2)
    
    print(f"Frontend JSON data generated successfully at {images_data_file}")
    print(f"Total images in frontend data: {len(frontend_data)} (including {len(frontend_data) - len(all_image_data)} from cache only)")
    
except Exception as e:
    print(f"Error generating frontend JSON data: {e}")

# 6. Generate README.md
print("\n--- Generating README.md ---")
try:
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write("# Vision Image Index\n\n")
        f.write(f"This README automatically indexes images found in the repository. Last updated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n\n")
        f.write("| Image | Filename | Description | Tags | Metadata | Hash |\n")
        f.write("|---|---|---|---|---|---|\n")

        all_image_data.sort(key=lambda x: x['path'])

        for data in all_image_data:
            # Use the normalized path for linking and display
            md_image_path = data['path'].replace('\\', '/') # Ensure forward slashes
            # URL encode the path for the image source URL to handle potential lingering characters if needed
            # Though normalization should prevent most issues. Using raw=true for GitHub rendering.
            encoded_path = md_image_path # Basic approach, consider urllib.parse.quote if complex chars remain
            img_tag = f"![{os.path.basename(data['path'])}]({encoded_path}?raw=true)"

            meta_items = [
                f"Dims: {data['metadata'].get('dimensions', 'N/A')}",
                f"Format: {data['metadata'].get('format', 'N/A')}",
                f"Size: {data['metadata'].get('size_kb', 'N/A')}"
            ]
            meta_str = " <br> ".join(item for item in meta_items if 'N/A' not in item)
            if not meta_str: meta_str = "N/A"

            safe_description = data['description'].replace('|', '\\|') if data.get('description') else 'N/A'
            safe_tags = data['tags'].replace('|', '\\|') if data.get('tags') else 'N/A'

            f.write(f"| {img_tag} | `{data['path']}` | {safe_description} | `{safe_tags}` | {meta_str} | `{data['hash'][:12]}...` |\n")

    print(f"README.md generated successfully at {readme_file}")

except Exception as e:
    print(f"Error generating README.md: {e}")

# 7. Save Cache
print("\n--- Saving Cache ---")
hashes_in_repo = {item['hash'] for item in all_image_data if item.get('hash')} # Use .get for safety
hashes_to_keep = set(image_cache.keys()) & hashes_in_repo
cleaned_cache = {h: image_cache[h] for h in hashes_to_keep}

if len(cleaned_cache) < len(image_cache):
    print(f"Removed {len(image_cache) - len(cleaned_cache)} stale entries from cache (likely deleted images).")

save_cache(cleaned_cache, CACHE_FILE)

print("\nImage indexing complete.")
