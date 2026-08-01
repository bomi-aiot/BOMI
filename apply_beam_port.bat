@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ============================================================
echo  beam port -> ai-develop clean MR  (steps 0-4, then STOP)
echo ============================================================

echo [0] cleaning stale locks / worktree
if exist ".git\index.lock" del /f ".git\index.lock"
for /f "tokens=1" %%W in ('git worktree list ^| findstr port_wt') do git worktree remove -f -f "%%W"
git worktree prune >nul 2>&1

echo [1] backup current branch
git branch backup/171-old-structure 2>nul

echo [2] reset branch onto origin/ai-develop
git fetch origin || goto :err
git reset --hard origin/ai-develop || goto :err

echo [3] remove old-path stray files (avoid patch collision)
del /f "robot\ai_chat\tests\calibrate_beam.py" 2>nul
del /f "robot\ai_chat\tests\list_audio_devices.py" 2>nul
del /f "robot\ai_chat\tests\test_beam_manual.py" 2>nul
del /f "robot\ai_chat\src\audio_io\beam_control.py" 2>nul

echo [3b] apply port patch
git apply --whitespace=nowarn beam_port.patch || goto :err

echo [4] install + test
pushd robot\ai_chat
pip install -e ".[dev]"
python -m pytest -q
popd

echo.
echo ============================================================
echo  DONE (steps 0-4). Review, then run these to push + open MR:
echo.
echo    git add -A robot/ai_chat
echo    git commit -m "feat(ai): 4mic beamforming + weather intent + medical examples (ported to bomi_ai_chat)"
echo    git push --force-with-lease origin ai/feat/S15P11E102-171-ai-4-mic-beams-focused
echo.
echo  (helper files beam_port.patch / apply_beam_port.bat stay untracked - delete anytime)
echo  Then on GitLab: MR  this branch -> ai-develop  (no conflicts)
echo ============================================================
goto :eof
:err
echo.
echo [ERROR] stopped. check the message above. your work is safe:
echo   - backup branch: backup/171-old-structure
echo   - backup tag:    backup/before-port-20260731
