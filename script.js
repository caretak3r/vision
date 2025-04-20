document.addEventListener('DOMContentLoaded', function() {
    const imageGrid = document.getElementById('image-grid');
    const searchBar = document.getElementById('search-bar');
    const tooltip = document.getElementById('tooltip');
    
    let allImages = [];

    // Fetch the JSON data for the images
    fetch('images_data.json')
        .then(response => {
            if (!response.ok) {
                // If images_data.json doesn't exist yet, fall back to README parsing
                if (response.status === 404) {
                    return fetch('README.md')
                        .then(resp => resp.text())
                        .then(markdown => {
                            console.log('Using README.md as fallback data source');
                            return parseMarkdownTable(markdown);
                        });
                }
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Store the image data
            allImages = data;
            
            // Render all images initially
            renderImages(allImages);
            
            // Setup search functionality
            setupSearch();
        })
        .catch(error => {
            console.error('Error fetching image data:', error);
            imageGrid.innerHTML = '<p class="error">Error loading image data. Please try again later.</p>';
        });

    // Fallback function to parse the markdown table if JSON file is not available
    function parseMarkdownTable(markdown) {
        const lines = markdown.split('\n');
        const imageData = [];
        
        // Find the table start (after header rows)
        let tableStartIndex = 0;
        for (let i = 0; i < lines.length; i++) {
            if (lines[i].includes('---|---|---|---|---|---')) {
                tableStartIndex = i + 1;
                break;
            }
        }
        
        // Parse each table row
        for (let i = tableStartIndex; i < lines.length; i++) {
            const line = lines[i].trim();
            if (!line || line.startsWith('#')) continue; // Skip empty lines or new sections
            
            // Split the line by the pipe character, but keep the content inside markdown image tags together
            const columns = splitTableRow(line);
            if (columns.length < 6) continue; // Skip invalid rows
            
            // Extract image path from the img tag
            const imgTagMatch = columns[0].match(/!\[.*?\]\((.*?)(?:\?.*?)?\)/);
            if (!imgTagMatch) continue;
            
            const path = imgTagMatch[1];
            const filename = columns[1].replace(/`/g, '').trim();
            const description = columns[2].trim();
            
            // Extract and clean tags - remove backticks and split by comma
            const tagsText = columns[3].replace(/`/g, '').trim();
            const tags = tagsText.split(',').map(tag => tag.trim());
            
            // Extract metadata
            const metadata = columns[4].replace(/<br>/g, ', ').trim();
            
            // Extract hash
            const hash = columns[5].replace(/`/g, '').trim();
            
            imageData.push({
                path,
                filename,
                description,
                tags,
                metadata: { raw: metadata },
                hash
            });
        }
        
        return imageData;
    }
    
    // Helper function for README markdown parsing
    function splitTableRow(row) {
        const columns = [];
        let currentColumn = "";
        let insideImage = false;
        
        for (let i = 0; i < row.length; i++) {
            const char = row[i];
            
            if (char === '!' && row[i+1] === '[') {
                insideImage = true;
                currentColumn += char;
            } else if (char === ')' && insideImage) {
                insideImage = false;
                currentColumn += char;
            } else if (char === '|' && !insideImage) {
                columns.push(currentColumn.trim());
                currentColumn = "";
            } else {
                currentColumn += char;
            }
        }
        
        // Add the last column
        if (currentColumn.trim()) {
            columns.push(currentColumn.trim());
        }
        
        return columns;
    }
    
    // Render images in the grid
    function renderImages(images) {
        imageGrid.innerHTML = '';
        
        if (images.length === 0) {
            imageGrid.innerHTML = '<p class="no-results">No images match your search criteria.</p>';
            return;
        }
        
        images.forEach(image => {
            const imageItem = document.createElement('div');
            imageItem.className = 'image-item';
            imageItem.dataset.path = image.path;
            imageItem.dataset.tags = JSON.stringify(image.tags);
            
            const tagsHtml = image.tags.map(tag => `<span class="tag">${tag}</span>`).join('');
            
            // Format metadata based on its structure
            let metadataHtml = '';
            if (image.metadata) {
                if (image.metadata.raw) {
                    // For data parsed from README
                    metadataHtml = image.metadata.raw;
                } else {
                    // For data from JSON
                    const meta = [];
                    if (image.metadata.dimensions && image.metadata.dimensions !== 'N/A') {
                        meta.push(`Dims: ${image.metadata.dimensions}`);
                    }
                    if (image.metadata.format && image.metadata.format !== 'N/A') {
                        meta.push(`Format: ${image.metadata.format}`);
                    }
                    if (image.metadata.size_kb && image.metadata.size_kb !== 'N/A') {
                        meta.push(`Size: ${image.metadata.size_kb}`);
                    }
                    metadataHtml = meta.join(', ');
                }
            }
            
            imageItem.innerHTML = `
                <img src="${image.path}" alt="${image.filename}" class="image-thumbnail">
                <div class="image-info">
                    <div class="image-path">${image.filename}</div>
                    <div class="image-description">${image.description}</div>
                    <div class="image-tags">${tagsHtml}</div>
                    <div class="image-metadata">${metadataHtml}</div>
                </div>
            `;
            
            // Add hover functionality for tooltip
            imageItem.addEventListener('mouseenter', function(e) {
                showTooltip(image.path);
            });
            
            imageItem.addEventListener('mousemove', function(e) {
                positionTooltip(e);
            });
            
            imageItem.addEventListener('mouseleave', function() {
                hideTooltip();
            });
            
            // Add click functionality to open full-size image
            imageItem.addEventListener('click', function() {
                openFullSizeImage(image.path);
            });
            
            imageGrid.appendChild(imageItem);
        });
    }
    
    // Setup search functionality
    function setupSearch() {
        searchBar.addEventListener('input', function() {
            const searchTerms = this.value.toLowerCase().split(' ').filter(term => term.trim() !== '');
            
            if (searchTerms.length === 0) {
                renderImages(allImages);
                return;
            }
            
            const filteredImages = allImages.filter(image => {
                return searchTerms.every(term => {
                    return image.tags.some(tag => tag.toLowerCase().includes(term));
                });
            });
            
            renderImages(filteredImages);
        });
    }
    
    // Show tooltip with full-size image
    function showTooltip(imagePath) {
        tooltip.innerHTML = `<img src="${imagePath}" alt="Full-size preview">`;
        tooltip.style.display = 'block';
    }
    
    // Position tooltip near the cursor
    function positionTooltip(event) {
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const tooltipWidth = tooltip.offsetWidth;
        const tooltipHeight = tooltip.offsetHeight;
        
        // Calculate tooltip position based on cursor location
        let left = event.pageX + 20;
        let top = event.pageY + 20;
        
        // Adjust position if tooltip would go outside viewport
        if (left + tooltipWidth > viewportWidth) {
            left = event.pageX - tooltipWidth - 10;
        }
        
        if (top + tooltipHeight > viewportHeight) {
            top = event.pageY - tooltipHeight - 10;
        }
        
        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    }
    
    // Hide tooltip
    function hideTooltip() {
        tooltip.style.display = 'none';
    }
    
    // Open full-size image in a modal or new window
    function openFullSizeImage(imagePath) {
        // Using a simple approach: open the image in a new tab/window
        window.open(imagePath, '_blank');
    }
});
