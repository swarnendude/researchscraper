# Link Scraper

A simple Flask web app that extracts URLs from text or documents and scrapes their content into a single markdown file.

## Features

- **Paste text** containing URLs directly
- **Upload PDF or DOCX files** - extracts both visible URLs and embedded hyperlinks
- **Progress tracking** - see real-time scraping progress
- **Download results** - get all scraped content as a single markdown file

## Installation

```bash
# Clone the repository
git clone https://github.com/swarnendude/researchscraper.git
cd researchscraper

# Install dependencies
pip install -r requirements.txt

# Run the app
python app.py
```

Then open http://localhost:5000 in your browser.

## Requirements

- Python 3.7+
- Flask
- BeautifulSoup4
- PyPDF2
- python-docx
- requests

## Usage

1. **Option A:** Paste text containing URLs into the text area
2. **Option B:** Upload a PDF or DOCX file (supports drag & drop)
3. Click **"Scrape Links"**
4. Wait for scraping to complete
5. Click **"Download Markdown"** to get the results

## How It Works

- Extracts URLs using regex pattern matching
- For PDF/DOCX files, also extracts embedded hyperlinks (clickable text links)
- Scrapes each URL and extracts the main content
- Combines everything into a formatted markdown document

## License

MIT
