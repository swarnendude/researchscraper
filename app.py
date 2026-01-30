import re
import os
import uuid
import requests
from flask import Flask, render_template, request, jsonify, send_file
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import tempfile
from werkzeug.utils import secure_filename
import io

# PDF and DOCX parsing
import PyPDF2
from docx import Document
import zipfile
import xml.etree.ElementTree as ET

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

ALLOWED_EXTENSIONS = {'pdf', 'docx'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_from_pdf(file_stream):
    """Extract text and hyperlinks from PDF file."""
    try:
        reader = PyPDF2.PdfReader(file_stream)
        text = ''
        urls = set()

        for page in reader.pages:
            # Extract visible text
            text += page.extract_text() + '\n'

            # Extract hyperlinks from annotations
            if '/Annots' in page:
                annotations = page['/Annots']
                if annotations:
                    for annot in annotations:
                        annot_obj = annot.get_object()
                        if annot_obj.get('/Subtype') == '/Link':
                            if '/A' in annot_obj:
                                action = annot_obj['/A']
                                if '/URI' in action:
                                    uri = action['/URI']
                                    if uri and uri.startswith(('http://', 'https://')):
                                        urls.add(uri)

        # Append extracted URLs to text so they get picked up
        if urls:
            text += '\n\n--- Extracted Hyperlinks ---\n'
            for url in urls:
                text += url + '\n'

        return text
    except Exception as e:
        raise ValueError(f'Failed to parse PDF: {str(e)}')


def extract_text_from_docx(file_stream):
    """Extract text and hyperlinks from DOCX file."""
    try:
        # First, extract hyperlinks from the raw XML (more reliable)
        urls = set()
        file_stream.seek(0)

        with zipfile.ZipFile(file_stream, 'r') as zf:
            # Extract hyperlinks from document.xml.rels
            if 'word/_rels/document.xml.rels' in zf.namelist():
                rels_xml = zf.read('word/_rels/document.xml.rels')
                rels_root = ET.fromstring(rels_xml)
                for rel in rels_root.iter():
                    if rel.get('Type') and 'hyperlink' in rel.get('Type', '').lower():
                        target = rel.get('Target', '')
                        if target.startswith(('http://', 'https://')):
                            urls.add(target)

            # Also check for URLs in the document text itself
            if 'word/document.xml' in zf.namelist():
                doc_xml = zf.read('word/document.xml')
                # Find any http/https URLs in the raw XML
                url_matches = re.findall(r'https?://[^\s<>"\']+', doc_xml.decode('utf-8', errors='ignore'))
                for url in url_matches:
                    url = url.rstrip('.,;:!?)')
                    if url.startswith(('http://', 'https://')):
                        urls.add(url)

        # Now extract text using python-docx
        file_stream.seek(0)
        doc = Document(file_stream)
        text = ''

        for para in doc.paragraphs:
            text += para.text + '\n'

        # Also extract from tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text += cell.text + '\n'

        # Append extracted URLs to text so they get picked up
        if urls:
            text += '\n\n--- Extracted Hyperlinks ---\n'
            for url in urls:
                text += url + '\n'

        return text
    except Exception as e:
        raise ValueError(f'Failed to parse DOCX: {str(e)}')

# Store scraping results temporarily
scrape_results = {}


def extract_urls(text):
    """Extract URLs from text content."""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    urls = re.findall(url_pattern, text)
    # Clean up URLs (remove trailing punctuation)
    cleaned = []
    for url in urls:
        url = url.rstrip('.,;:!?)')
        if url and urlparse(url).netloc:
            cleaned.append(url)
    return list(dict.fromkeys(cleaned))  # Remove duplicates, preserve order


def scrape_url(url, timeout=10):
    """Scrape content from a single URL."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove script and style elements
        for element in soup(['script', 'style', 'nav', 'footer', 'header']):
            element.decompose()

        # Get title
        title = soup.title.string if soup.title else url

        # Get main content - try common content containers
        content = None
        for selector in ['article', 'main', '.content', '#content', '.post', '.article']:
            content = soup.select_one(selector)
            if content:
                break

        if not content:
            content = soup.body if soup.body else soup

        # Extract text
        text = content.get_text(separator='\n', strip=True)

        # Clean up excessive whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        text = '\n\n'.join(lines)

        # Limit content length
        if len(text) > 5000:
            text = text[:5000] + '\n\n[Content truncated...]'

        return {
            'success': True,
            'title': title.strip() if title else url,
            'content': text,
            'url': url
        }
    except Exception as e:
        return {
            'success': False,
            'title': url,
            'content': f'Error scraping: {str(e)}',
            'url': url
        }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and extract text."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Only PDF and DOCX allowed'}), 400

    try:
        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[1].lower()

        # Read file into memory
        file_stream = io.BytesIO(file.read())

        if ext == 'pdf':
            text = extract_text_from_pdf(file_stream)
        elif ext == 'docx':
            text = extract_text_from_docx(file_stream)
        else:
            return jsonify({'error': 'Unsupported file type'}), 400

        return jsonify({'text': text, 'filename': filename})

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Failed to process file: {str(e)}'}), 500


@app.route('/scrape', methods=['POST'])
def scrape():
    data = request.json
    text = data.get('text', '')

    urls = extract_urls(text)
    if not urls:
        return jsonify({'error': 'No URLs found in the text'}), 400

    # Generate session ID
    session_id = str(uuid.uuid4())
    scrape_results[session_id] = {
        'urls': urls,
        'results': [],
        'total': len(urls),
        'completed': 0
    }

    return jsonify({
        'session_id': session_id,
        'total': len(urls),
        'urls': urls
    })


@app.route('/scrape/<session_id>/<int:index>', methods=['POST'])
def scrape_single(session_id, index):
    if session_id not in scrape_results:
        return jsonify({'error': 'Session not found'}), 404

    session = scrape_results[session_id]
    if index >= len(session['urls']):
        return jsonify({'error': 'Invalid index'}), 400

    url = session['urls'][index]
    result = scrape_url(url)

    # Store result
    while len(session['results']) <= index:
        session['results'].append(None)
    session['results'][index] = result
    session['completed'] = sum(1 for r in session['results'] if r is not None)

    return jsonify({
        'result': result,
        'completed': session['completed'],
        'total': session['total']
    })


@app.route('/download/<session_id>')
def download(session_id):
    if session_id not in scrape_results:
        return jsonify({'error': 'Session not found'}), 404

    session = scrape_results[session_id]

    # Build markdown document
    markdown = '# Scraped Content\n\n'
    markdown += f'Total URLs: {session["total"]}\n\n---\n\n'

    for result in session['results']:
        if result:
            status = '✓' if result['success'] else '✗'
            markdown += f'## {status} {result["title"]}\n\n'
            markdown += f'**URL:** {result["url"]}\n\n'
            markdown += result['content']
            markdown += '\n\n---\n\n'

    # Create temp file
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8')
    temp_file.write(markdown)
    temp_file.close()

    return send_file(
        temp_file.name,
        as_attachment=True,
        download_name='scraped_content.md',
        mimetype='text/markdown'
    )


if __name__ == '__main__':
    app.run(debug=True)
