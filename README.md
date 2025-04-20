# Vision Image Index

A dynamic image gallery for browsing, searching, and viewing a collection of images.

## Features

- **Automatic Image Indexing**: Images are automatically analyzed and categorized using the Gemini API
- **Full Metadata**: Each image includes tags, descriptions, and technical metadata
- **Interactive Search**: Filter images by tags in real-time as you type
- **Preview on Hover**: Hover over any image thumbnail to see a larger preview
- **Full Resolution View**: Click any image to open it in full resolution
- **GitHub Pages Integration**: Automatically deployed as a static site

## How It Works

1. **Image Processing**:
   - The `index_images.py` script scans the repository for image files
   - Images are normalized and analyzed for content using the Gemini API
   - Results are cached in `image_cache.json` to avoid redundant processing
   - A frontend-friendly data file (`images_data.json`) is generated

2. **GitHub Actions Automation**:
   - When new images are added or the code changes, a workflow is triggered
   - The indexing script runs, generating/updating metadata
   - Changes are committed back to the repository
   - The website is automatically deployed to GitHub Pages

3. **Web Interface**:
   - Simple HTML/CSS/JS frontend displays all indexed images
   - Search functionality filters images by tag
   - Hover over images to preview, click to view full resolution

## Development

To run this locally:

```bash
# Start a local web server
python -m http.server 8000

# Open in your browser
open http://localhost:8000
```

## Technical Details

- **Frontend**: Pure HTML, CSS, and vanilla JavaScript
- **Backend**: Python script for image processing and metadata generation
- **AI Integration**: Uses Google's Gemini API for image analysis and tag generation
- **Deployment**: GitHub Actions + GitHub Pages for fully automated workflow
