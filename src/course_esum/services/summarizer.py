import hashlib
import json
from typing import List, Tuple, Optional
from google import genai
from google.genai import types
from course_esum.config import get_settings
from course_esum.schemas.evaluation import CourseEvaluationSummary
from course_esum.services.gemini_retry import GeminiRetryConfig, with_gemini_retry

class SummarizerService:
    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = settings.GEMINI_MODEL
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY is not configured.")
        self.client = genai.Client(api_key=self.api_key)
        self._retry_cfg = GeminiRetryConfig(
            max_retries=settings.GEMINI_MAX_RETRIES,
            base_delay_ms=settings.GEMINI_BASE_DELAY_MS,
            max_delay_ms=settings.GEMINI_MAX_DELAY_MS,
        )

    @staticmethod
    def compute_hash(data: bytes) -> str:
        """Computes SHA-256 hash for document caching."""
        return hashlib.sha256(data).hexdigest()

    def summarize_from_text(self, text: str, output_language: str = "English") -> CourseEvaluationSummary:
        """Deterministic summarization of course evaluation text."""
        prompt = f"""
You are an expert academic assistant that analyzes and summarizes university course evaluations.
Your task is to analyze the provided course evaluation text and fill in the requested JSON structure.

CRITICAL INSTRUCTIONS:
1. ONLY use the provided text. Do NOT hallucinate, guess, or invent any information.
2. If the text does not contain information for a specific field, output "No information available" or an empty list.
3. Keep the bullet points concise, factual, and strictly based on the text.
4. Provide the final output in the following language: {output_language}
5. COHORT METRICS: Search the text for student response and registration counts.
   - Look for patterns like "X of Y students", "X av Y studenter", "svarsfrekvens", "antal svar", "antal registrerade",
     or table headers that list respondents vs total enrolled.
   - Set `respondents_count` to the total number of students who answered.
   - Set `registered_count` to the total number of students registered/enrolled.
   - Set `response_rate_percent` to (respondents_count / registered_count * 100) rounded to 1 decimal.
   - If any of these figures are absent from the text, set the corresponding field to null.
   - If multiple terms are present, sum the counts across all terms.

Course Evaluation Text:
{text}
        """

        response = with_gemini_retry(
            self.client.models.generate_content,
            cfg=self._retry_cfg,
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CourseEvaluationSummary,
                temperature=0.0,
            ),
        )
        
        parsed = json.loads(response.text)
        return CourseEvaluationSummary.model_validate(parsed)

    def summarize_from_pdf_documents(
        self,
        documents: List[Tuple[str, bytes]],
        output_language: str = "English"
    ) -> CourseEvaluationSummary:
        """
        Multimodal PDF summarization: sends native PDF bytes directly to Gemini 2.5 Flash,
        preserving tables, graphs, and multi-column layouts across evaluation terms.
        """
        prompt = f"""
You are an expert academic assistant analyzing university course evaluation reports ('kursutvärderingsanalyser').
Analyze the attached official PDF document(s) and populate the structured evaluation summary.

CRITICAL INSTRUCTIONS:
1. Ground every point strictly in the attached evaluation reports.
2. Pay attention to both statistical scores (means, question responses) and written qualitative reflections.
3. If evaluating multiple terms or academic years, synthesize the overall trajectory in 'trend_over_time'.
4. Do NOT hallucinate or guess.
5. Provide the output in the requested language: {output_language}
6. COHORT METRICS: Locate the student response and registration counts in each attached document.
   - Common Swedish labels: "Antal svar" (respondents), "Antal registrerade" (registered),
     "svarsfrekvens" (response rate), or similar columns/rows in summary tables.
   - Set `respondents_count` to the total number of students who responded across all attached reports.
   - Set `registered_count` to the total number of registered students across all attached reports.
   - Set `response_rate_percent` to (respondents_count / registered_count * 100) rounded to 1 decimal.
   - If these figures cannot be found in the documents, set those fields to null — do not estimate.
   - If multiple documents are provided, sum the counts across all of them.
        """

        contents: list = [prompt]
        for label, pdf_bytes in documents:
            contents.append(f"\n--- Attached Document Period: {label} ---")
            contents.append(
                types.Part.from_bytes(
                    data=pdf_bytes,
                    mime_type="application/pdf"
                )
            )

        response = with_gemini_retry(
            self.client.models.generate_content,
            cfg=self._retry_cfg,
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CourseEvaluationSummary,
                temperature=0.0,
            ),
        )

        parsed = json.loads(response.text)
        return CourseEvaluationSummary.model_validate(parsed)
