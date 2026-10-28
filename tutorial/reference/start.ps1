$ErrorActionPreference = 'Stop'
$python = 'C:\Users\13480\miniconda3\envs\yolo_v5_obb\python.exe'
$env:PYTHONIOENCODING = 'utf-8'
& $python -B (Join-Path $PSScriptRoot 'start.py')
