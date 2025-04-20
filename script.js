document.addEventListener('DOMContentLoaded', function() {
    const imageGrid = document.getElementById('image-grid');
    const searchBar = document.getElementById('search-bar');
    const tooltip = document.getElementById('tooltip');
    
    let allImages = [];

    const metricsBar = document.getElementById('metrics-bar');

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
            
            // Calculate and display metrics
            calculateAndDisplayMetrics(allImages);
            
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
    
    // Calculate metrics from the image collection and display them
    function calculateAndDisplayMetrics(images) {
        // Filter out any images that are cached_only
        const activeImages = images.filter(img => !img.cached_only);
        
        // 1. Total number of images
        const totalImages = activeImages.length;
        
        // 2. Collect all unique tags
        const uniqueTags = new Set();
        activeImages.forEach(image => {
            if (Array.isArray(image.tags)) {
                image.tags.forEach(tag => uniqueTags.add(tag.toLowerCase()));
            }
        });
        const totalUniqueTags = uniqueTags.size;
        
        // 3. Find image(s) with the most tags
        let maxTagCount = 0;
        let imagesWithMostTags = [];
        
        activeImages.forEach(image => {
            if (Array.isArray(image.tags)) {
                const tagCount = image.tags.length;
                if (tagCount > maxTagCount) {
                    maxTagCount = tagCount;
                    imagesWithMostTags = [image.filename];
                } else if (tagCount === maxTagCount) {
                    imagesWithMostTags.push(image.filename);
                }
            }
        });
        
        // Format the max tags display text
        let maxTagsText = `${maxTagCount} tags`;
        if (imagesWithMostTags.length > 0) {
            const shortName = imagesWithMostTags[0].split('/').pop();
            maxTagsText = `${maxTagCount} (${shortName})`;
        }
        
        // 4. Calculate average tags per image
        const avgTags = activeImages.length > 0 
            ? (activeImages.reduce((sum, img) => sum + (Array.isArray(img.tags) ? img.tags.length : 0), 0) / activeImages.length).toFixed(1)
            : 0;
            
        // 5. Find most common tags
        const tagFrequency = {};
        activeImages.forEach(image => {
            if (Array.isArray(image.tags)) {
                image.tags.forEach(tag => {
                    const normalizedTag = tag.toLowerCase();
                    tagFrequency[normalizedTag] = (tagFrequency[normalizedTag] || 0) + 1;
                });
            }
        });
        
        // Get the most common tag(s)
        let mostCommonTags = [];
        let maxFrequency = 0;
        for (const [tag, frequency] of Object.entries(tagFrequency)) {
            if (frequency > maxFrequency) {
                mostCommonTags = [tag];
                maxFrequency = frequency;
            } else if (frequency === maxFrequency) {
                mostCommonTags.push(tag);
            }
        }
        
        // Format most common tag display
        const commonTagDisplay = mostCommonTags.length > 0 
            ? `${mostCommonTags[0]} (${maxFrequency})`
            : 'None';
            
        // 6. Analyze file formats
        const formatCounts = {};
        activeImages.forEach(image => {
            let format = 'unknown';
            if (image.metadata) {
                if (image.metadata.format && image.metadata.format !== 'N/A') {
                    format = image.metadata.format.toLowerCase();
                } else if (image.metadata.raw && image.metadata.raw.includes('Format:')) {
                    const formatMatch = image.metadata.raw.match(/Format: (\w+)/);
                    if (formatMatch) format = formatMatch[1].toLowerCase();
                } else if (image.path) {
                    // Try to get format from file extension
                    const ext = image.path.split('.').pop().toLowerCase();
                    if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'].includes(ext)) {
                        format = ext === 'jpg' ? 'jpeg' : ext;
                    }
                }
            }
            formatCounts[format] = (formatCounts[format] || 0) + 1;
        });
        
        // Get the most common format
        let mostCommonFormat = 'unknown';
        let maxFormatCount = 0;
        for (const [format, count] of Object.entries(formatCounts)) {
            if (count > maxFormatCount) {
                mostCommonFormat = format;
                maxFormatCount = count;
            }
        }
        
        // Format display text for file formats
        const formatText = Object.keys(formatCounts).length > 0
            ? `${mostCommonFormat.toUpperCase()} (${maxFormatCount})`
            : 'None';
            
        // 7. Calculate total collection size
        let totalSizeKB = 0;
        activeImages.forEach(image => {
            // Extract size from metadata
            if (image.metadata) {
                let sizeStr;
                if (image.metadata.size_kb) {
                    sizeStr = image.metadata.size_kb;
                } else if (image.metadata.raw && image.metadata.raw.includes('Size:')) {
                    sizeStr = image.metadata.raw.match(/Size: ([\d\.]+) KB/)?.[1] || '0';
                }
                
                if (sizeStr) {
                    // Extract the number from the size string
                    const sizeMatch = sizeStr.match(/([\d\.]+)/);
                    if (sizeMatch) {
                        totalSizeKB += parseFloat(sizeMatch[1]);
                    }
                }
            }
        });
        
        // Format the size for display (convert to MB if over 1000 KB)
        let formattedSize;
        if (totalSizeKB > 1000) {
            formattedSize = `${(totalSizeKB / 1000).toFixed(2)} MB`;
        } else {
            formattedSize = `${totalSizeKB.toFixed(2)} KB`;
        }
        
        // 8. Create metrics HTML
        const metricsHTML = `
            <div class="metric-item">
                <div class="metric-title">Total Images</div>
                <div class="metric-value">${totalImages}</div>
            </div>
            <div class="metric-item">
                <div class="metric-title">Unique Tags</div>
                <div class="metric-value">${totalUniqueTags}</div>
            </div>
            <div class="metric-item">
                <div class="metric-title">Most Tagged</div>
                <div class="metric-value">${maxTagsText}</div>
            </div>
            <div class="metric-item">
                <div class="metric-title">Avg Tags/Image</div>
                <div class="metric-value">${avgTags}</div>
            </div>
            <div class="metric-item">
                <div class="metric-title">Most Common Tag</div>
                <div class="metric-value">${commonTagDisplay}</div>
            </div>
            <div class="metric-item">
                <div class="metric-title">Top Format</div>
                <div class="metric-value">${formatText}</div>
            </div>
            <div class="metric-item">
                <div class="metric-title">Collection Size</div>
                <div class="metric-value">${formattedSize}</div>
            </div>
        `;
        
        // Update the metrics bar
        metricsBar.innerHTML = metricsHTML;
        
        // Also update metrics when search is used
        searchBar.addEventListener('input', function() {
            const searchTerms = this.value.toLowerCase().split(' ').filter(term => term.trim() !== '');
            
            if (searchTerms.length === 0) {
                // If search is empty, show metrics for all images
                metricsBar.innerHTML = metricsHTML;
            } else {
                // Calculate metrics only for filtered images
                const filteredImages = allImages.filter(image => {
                    return searchTerms.every(term => {
                        return image.tags.some(tag => tag.toLowerCase().includes(term));
                    });
                });
                
                // Calculate tag statistics for filtered results
                const filteredUniqueTagsCount = new Set(
                    filteredImages.flatMap(img => 
                        Array.isArray(img.tags) ? img.tags.map(tag => tag.toLowerCase()) : []
                    )
                ).size;
                
                // Update the metrics bar with stats for filtered images
                metricsBar.innerHTML = `
                    <div class="metric-item">
                        <div class="metric-title">Matching Images</div>
                        <div class="metric-value">${filteredImages.length} / ${totalImages}</div>
                    </div>
                    <div class="metric-item">
                        <div class="metric-title">Filter Tags</div>
                        <div class="metric-value">${filteredUniqueTagsCount} / ${totalUniqueTags}</div>
                    </div>
                    <div class="metric-item">
                        <div class="metric-title">Most Tagged</div>
                        <div class="metric-value">${maxTagsText}</div>
                    </div>
                    <div class="metric-item">
                        <div class="metric-title">Most Common Tag</div>
                        <div class="metric-value">${commonTagDisplay}</div>
                    </div>
                    <div class="metric-item">
                        <div class="metric-title">Top Format</div>
                        <div class="metric-value">${formatText}</div>
                    </div>
                    <div class="metric-item">
                        <div class="metric-title">Collection Size</div>
                        <div class="metric-value">${formattedSize}</div>
                    </div>
                `;
            }
        });
    }
});
