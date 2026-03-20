@echo off
setlocal

if not exist venv (
  python -m venv venv
)

call venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

pyinstaller --noconfirm --clean --onefile --windowed --name DoubaoVideoLinkTool doubao_video_link_gui.py

echo.
echo Build completed.
echo EXE path: dist\DoubaoVideoLinkTool.exe
pause
