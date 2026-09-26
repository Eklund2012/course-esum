import io
import re
import urllib.request
import urllib.error
from typing import List, Dict, Any
from pypdf import PdfReader

def extract_text_from_bytes(pdf_bytes_io: io.BytesIO) -> str:
    """Extracts all text from in-memory PDF BytesIO."""
    reader = PdfReader(pdf_bytes_io)
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
    return text

def fetch_kau_evaluations(course_code: str, max_reports: int = 3) -> Dict[str, Any]:
    """
    Fetches official Karlstad University course evaluation reports ('kursutvärderingsanalyser').
    
    Args:
        course_code: Course code, e.g. 'DVAE24' or 'DVAE23'.
        max_reports: Maximum number of recent reports to download (default: 3).
        
    Returns:
        Dict containing:
            - course_code: Normalized uppercase course code
            - course_title: Extracted human-readable course name
            - reports: List of dicts with 'label', 'url', 'pdf_bytes', and 'extracted_text'
            - combined_text: Combined text from all fetched reports
    """
    clean_code = course_code.strip().upper()
    url = f"https://www.kau.se/utbildning/program-och-kurser/kurser/{clean_code}"
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"Course '{clean_code}' was not found at Karlstad University ({url}).")
        raise RuntimeError(f"Failed to fetch course page from KAU (HTTP {e.code}): {e.reason}")
    except Exception as e:
        raise RuntimeError(f"Network error connecting to Karlstad University: {e}")

    # Extract Course Title
    title_match = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"|]+)', html, re.IGNORECASE)
    course_title = title_match.group(1).strip() if title_match else clean_code

    # Extract evaluation PDF links
    pattern = r'href=[\'"](https://www3\.kau\.se/kursvarderingsanalyser/[^\'"]+\.pdf)[\'"][^>]*>(.*?)</a>'
    matches = re.findall(pattern, html, re.IGNORECASE)
    
    if not matches:
        raise ValueError(f"No course evaluation reports ('kursutvärderingsanalyser') are available for course '{clean_code}'.")

    reports = []
    combined_texts = []

    for pdf_url, label in matches[:max_reports]:
        clean_label = " ".join(label.replace("PDF", "").split())
        pdf_req = urllib.request.Request(
            pdf_url,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        try:
            with urllib.request.urlopen(pdf_req, timeout=15) as pdf_resp:
                pdf_data = pdf_resp.read()
                pdf_stream = io.BytesIO(pdf_data)
                text = extract_text_from_bytes(pdf_stream)
                
                reports.append({
                    "label": clean_label,
                    "url": pdf_url,
                    "pdf_bytes": pdf_stream,
                    "extracted_text": text
                })
                combined_texts.append(f"--- EVALUATION REPORT: {clean_label} ---\n{text}")
        except Exception as e:
            # Continue if one individual report fails
            continue

    if not reports:
        raise RuntimeError(f"Failed to download evaluation reports for course '{clean_code}'.")

    return {
        "course_code": clean_code,
        "course_title": course_title,
        "reports": reports,
        "combined_text": "\n\n".join(combined_texts)
    }
