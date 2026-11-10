@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
rem Proof renders for the Filter Forge driver: the bundled "Wet Stone" texture (Library_242-5) at 1024x1024.
rem   filter_forge_proof.bat                     final image only (factory preset 0, Seamless Tiling on)
rem   filter_forge_proof.bat <normal> [height]   + the normal map (and the height map) from presets YOU saved:
rem       in Filter Forge open Wet Stone, Render Channels menu -> Normal, Presets tab -> Add Preset; same for Height.
rem       filter_forge.bat presets Library_242-5 shows the factory numbers (0-6); yours come after (7, 8, ...).
rem       With a height map too, the forge checks the normal map is OpenGL (green = up) and fixes it if not.
rem Queued at priority 10 (CPU only — runs between two bake-off renders). Results: out\<job id>\contact.png
if not exist venv (echo Run install.bat first. & pause & exit /b 1)
call venv\Scripts\activate.bat
set "FF=C:\Program Files\Filter Forge 9\Resources\System\Library\Library_242-5.ffxml"
set "J=out\_tests\night3b\ff_proof_channels.json"
if not exist "out\_tests\night3b" mkdir "out\_tests\night3b"
if "%~1"=="" (
  python -c "import json,sys; json.dump({'type':'filter_forge','name':'g14_ff_proof_final','batch':'night3_proof','priority':10,'filter':sys.argv[1],'preset':0,'size':[1024,1024],'seamless':True,'channels':['final'],'slot_name':'wet_stone'}, open(sys.argv[2],'w'), indent=1)" "%FF%" "%J%"
) else if "%~2"=="" (
  python -c "import json,sys; json.dump({'type':'filter_forge','name':'g14_ff_proof_normal','batch':'night3_proof','priority':10,'filter':sys.argv[1],'size':[1024,1024],'seamless':True,'channels':{'final':0,'normal':int(sys.argv[3])},'slot_name':'wet_stone'}, open(sys.argv[2],'w'), indent=1)" "%FF%" "%J%" %1
) else (
  python -c "import json,sys; json.dump({'type':'filter_forge','name':'g14_ff_proof_normal_height','batch':'night3_proof','priority':10,'filter':sys.argv[1],'size':[1024,1024],'seamless':True,'channels':{'final':0,'normal':int(sys.argv[3]),'height':int(sys.argv[4])},'slot_name':'wet_stone'}, open(sys.argv[2],'w'), indent=1)" "%FF%" "%J%" %1 %2
)
python -m forge submit "%J%"
echo The worker picks it up between two renders (run_worker.bat must be running). Then look at out\^<job id^>\contact.png
pause
