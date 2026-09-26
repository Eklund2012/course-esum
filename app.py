import streamlit as st
import json
import os
from pdf_processor import extract_text_from_pdf, summarize_evaluations
from kau_fetcher import fetch_kau_evaluations

st.set_page_config(page_title="Course Evaluations - Summary", page_icon="🎓", layout="wide")

st.title("🎓 Smart Course Evaluation Summarizer")
st.write("Analyze university course evaluations using AI. Type a Karlstad University course code to fetch official reports automatically, or upload your own PDFs.")

# Initialize session state for caching summary results
if "current_summary" not in st.session_state:
    st.session_state.current_summary = None
if "current_reports" not in st.session_state:
    st.session_state.current_reports = []

# Sidebar for settings / input
with st.sidebar:
    st.header("Settings")
    demo_mode = st.checkbox("Use Demo Data", value=False, help="Loads a mock JSON to see the UI without calling the AI.")
    
    output_language = st.selectbox("Output Language", options=["English", "Swedish"])
    
    st.divider()
    
    input_method = st.radio(
        "Input Method",
        options=["Enter Course Code (Karlstad Univ.)", "Upload PDFs"]
    )
    
    uploaded_files = None
    course_code = None
    max_reports = 3
    
    if input_method == "Upload PDFs":
        uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)
    else:
        course_code = st.text_input("Course Code", value="DVAE24", placeholder="e.g., DVAE24, DVAE23, ISGB11")
        max_reports = st.slider("Max Reports to Analyze", min_value=1, max_value=5, value=3, help="How many recent yearly evaluation reports to download and analyze.")
        st.caption("Fetches official 'kursutvärderingsanalyser' directly from kau.se")

    process_btn = st.button("Generate Summary", type="primary", use_container_width=True)

def render_summary(data: dict):
    """Render Streamlit cards for the results"""
    st.header(data.get("course_name_and_code", "Unknown Course"))
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("👍 Positive Aspects")
        for p in data.get("positive_summary", []):
            st.success(f"• {p}")
            
    with col2:
        st.subheader("👎 Areas for Improvement / Critique")
        for k in data.get("critique_summary", []):
            st.error(f"• {k}")
            
    st.markdown("---")
    
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("⚖️ Workload")
        st.info(data.get("workload", "No information"))
        
    with col4:
        st.subheader("📈 Trend Over Time")
        st.warning(data.get("trend_over_time", "No information"))

if process_btn:
    if demo_mode:
        try:
            with open("demo.json", "r", encoding="utf-8") as f:
                demo_data = json.load(f)
            st.session_state.current_summary = demo_data
            st.session_state.current_reports = []
        except Exception as e:
            st.error(f"Could not load demo data: {e}")
            
    elif input_method == "Enter Course Code (Karlstad Univ.)":
        if not course_code.strip():
            st.warning("Please enter a course code (e.g., DVAE24).")
        else:
            code = course_code.strip().upper()
            with st.spinner(f"🔍 Fetching official course evaluation reports for {code} from Karlstad University..."):
                try:
                    fetch_data = fetch_kau_evaluations(code, max_reports=max_reports)
                    reports = fetch_data["reports"]
                    st.session_state.current_reports = reports
                    
                    st.success(f"Found {len(reports)} evaluation report(s) for **{fetch_data['course_title']}** ({code})")
                    
                    with st.spinner(f"🤖 Analyzing {len(reports)} evaluation report(s) with Gemini AI..."):
                        summary_data = summarize_evaluations(fetch_data["combined_text"], output_language)
                        st.session_state.current_summary = summary_data
                except ValueError as ve:
                    st.warning(str(ve))
                except Exception as e:
                    st.error(f"An error occurred: {e}")

    else:
        if not uploaded_files:
            st.warning("Please upload at least one PDF file.")
        else:
            with st.spinner("Extracting text and analyzing with AI..."):
                try:
                    all_text = ""
                    for pdf in uploaded_files:
                        all_text += extract_text_from_pdf(pdf) + "\n"
                        
                    if not all_text.strip():
                        st.error("Could not extract any text from the files.")
                    else:
                        summary_data = summarize_evaluations(all_text, output_language)
                        st.session_state.current_summary = summary_data
                        st.session_state.current_reports = []
                except ValueError as ve:
                    st.error(str(ve))
                except Exception as e:
                    st.error(f"An error occurred: {e}")

# Render cached summary if available
if st.session_state.current_summary:
    if st.session_state.current_reports:
        with st.expander(f"📄 Analyzed Reports ({len(st.session_state.current_reports)})", expanded=False):
            for r in st.session_state.current_reports:
                st.markdown(f"- **{r['label']}**: [Open PDF]({r['url']})")
    render_summary(st.session_state.current_summary)

