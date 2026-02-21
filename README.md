# ChartTool Python Module

This directory contains the Python-based components of the ChartTool project, including the main analysis dashboard and utility scripts for code quality management.

## Project Structure

- `app.py`: The main Streamlit-based web application. It provides real-time stock charting, technical indicator analysis, and AI-driven insights (Gemini & DCF).
- `requirements.txt`: List of Python dependencies required for the module.
- `cat_lines.py`: Debugging utility for inspecting specific line contents in source files.

## Setup Instructions

### 1. Environment Preparation

It is recommended to use a virtual environment:

```bash
# Create a virtual environment
python -m venv .venv

# Activate the environment (Windows)
.venv\Scripts\activate

# Activate the environment (Linux/macOS)
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configuration

Ensure you have a `.env` file in the project root with the following keys:

- `GEMINI_API_KEY`: For AI analysis features.
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: For Google OAuth2 login.
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: For automated alerts.

## Running the Application

To start the main analysis dashboard:

```bash
streamlit run app.py
```
