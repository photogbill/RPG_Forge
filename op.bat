@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem The forge's CPU tools as direct commands (no job file needed):
rem   op.bat tiles-demo                                    split / repaint / merge test on a 6144x3072 picture
rem   op.bat state-mask --base a.png --state b.png --out mask.png
rem   op.bat facings-pack --in poses_folder --out out_folder [--mirror W>E,NW>NE,SW>SE]
rem   op.bat anim-preview --in sheet.png --out out_folder [--fps 8]
rem   op.bat turnaround-split --in turnaround.png --out out_folder
rem   op.bat nine-slice --in panel.png --out out_folder [--margins 24,24,24,24] [--key auto]
rem   op.bat button-states --in button.png --out out_folder
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
python -m forge op %*
pause
