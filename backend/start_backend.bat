@echo off
cd /d C:\Users\juand\OneDrive\Desktop\Asistente_personal\backend
call .venv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --loop asyncio:SelectorEventLoop --log-level info > backend.log 2>&1