import os
import json
from pypdf import PdfReader
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from dotenv import load_dotenv

load_dotenv()

# Pydantic model to enforce structured output
class CourseEvaluationSummary(BaseModel):
    course_name_and_code: str = Field(description="The name of the course and its course code")
    positive_summary: list[str] = Field(description="A list of bullet points summarizing the positive aspects in the evaluation")
    critique_summary: list[str] = Field(description="A list of bullet points summarizing critique and areas for improvement")
    workload: str = Field(description="A short assessment of the workload (e.g., 'too high', 'appropriate', 'too low')")
    trend_over_time: str = Field(description="An analysis of how the evaluations have evolved over time if there is history")

def extract_text_from_pdf(pdf_file) -> str:
    """Extracts text from a PDF file (BytesIO object from Streamlit)"""
    reader = PdfReader(pdf_file)
    text = ""
    for page in reader.pages:
        extracted = page.extract_text()
        if extracted:
            text += extracted + "\n"
    return text

def summarize_evaluations(text: str, output_language: str = "English") -> dict:
    """Calls Gemini to summarize the course evaluation and returns JSON"""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing. Please set it in a .env file.")

    client = genai.Client(api_key=api_key)
    
    prompt = f"""
You are an assistant that analyzes and summarizes university course evaluations.
Your task is to read the provided text from course evaluations and fill in the requested JSON structure.

CRITICAL INSTRUCTIONS:
1. ONLY use the provided text. Do NOT hallucinate, guess, or invent any information.
2. If the text does not contain information for a specific field, output "No information available" or an empty list.
3. Keep the bullet points concise, factual, and strictly based on the text.
4. Provide the final output in the following language: {output_language}

Course Evaluation Text:
{text}
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CourseEvaluationSummary,
            temperature=0.0, # Deterministic output
        ),
    )
    
    return json.loads(response.text)
