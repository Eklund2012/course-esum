import io
import re
import urllib.request
import urllib.error
from pypdf import PdfReader
from course_esum.services.providers.base import CourseEvaluationProvider, CourseFetchResult, FetchedReport

class KarlstadUniversityProvider(CourseEvaluationProvider):
    """
    Provider for Karlstad University (kau.se).
    Scrapes the public course page and downloads official 'kursutvärderingsanalyser' PDF reports.
    """
    BASE_URL = "https://www.kau.se/utbildning/program-och-kurser/kurser"

    def fetch_evaluations(self, course_code: str, max_reports: int = 3) -> CourseFetchResult:
        clean_code = course_code.strip().upper()
        url = f"{self.BASE_URL}/{clean_code}"

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ValueError(f"Course '{clean_code}' not found at Karlstad University ({url}).")
            raise RuntimeError(f"KAU portal returned HTTP {e.code}: {e.reason}")
        except Exception as e:
            raise RuntimeError(f"Network error connecting to Karlstad University: {e}")

        # Parse course title
        title_match = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"|]+)', html, re.IGNORECASE)
        course_title = title_match.group(1).strip() if title_match else clean_code

        # Parse evaluation report PDF links
        pattern = r'href=[\'"](https://www3\.kau\.se/kursvarderingsanalyser/[^\'"]+\.pdf)[\'"][^>]*>(.*?)</a>'
        matches = re.findall(pattern, html, re.IGNORECASE)

        if not matches:
            raise ValueError(f"No course evaluation reports ('kursutvärderingsanalyser') found for '{clean_code}'.")

        reports: list[FetchedReport] = []
        for pdf_url, label in matches[:max_reports]:
            clean_label = " ".join(label.replace("PDF", "").split())
            pdf_req = urllib.request.Request(pdf_url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urllib.request.urlopen(pdf_req, timeout=15) as pdf_resp:
                    pdf_data = pdf_resp.read()
                    
                    # Optional text extraction for fallback
                    text = ""
                    try:
                        reader = PdfReader(io.BytesIO(pdf_data))
                        for page in reader.pages:
                            t = page.extract_text()
                            if t:
                                text += t + "\n"
                    except Exception:
                        pass

                    reports.append(FetchedReport(
                        label=clean_label,
                        url=pdf_url,
                        pdf_bytes=pdf_data,
                        extracted_text=text
                    ))
            except Exception:
                continue

        if not reports:
            raise RuntimeError(f"Failed to download evaluation reports for course '{clean_code}'.")

        return CourseFetchResult(
            course_code=clean_code,
            course_title=course_title,
            reports=reports
        )
