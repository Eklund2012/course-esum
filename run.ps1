$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m uvicorn course_esum.main:app --reload --port 8000

