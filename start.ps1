$ErrorActionPreference = 'Stop'
$python = 'C:\Users\13480\miniconda3\envs\yolo26obb\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
& $python -B (Join-Path $PSScriptRoot 'start.py')
