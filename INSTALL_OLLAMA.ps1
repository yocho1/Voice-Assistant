#!/usr/bin/env powershell

Write-Host "Installing Ollama on Windows..." -ForegroundColor Green
Write-Host "`nStep 1: Download Ollama"
Write-Host "Go to: https://ollama.ai/download/windows"
Write-Host "Click 'Download' and install the executable`n"

Write-Host "Step 2: Once installed, open a new PowerShell and run a model"
Write-Host "Execute one of these commands:`n"
Write-Host "  ollama run mistral       # Fast and good quality (recommended)"
Write-Host "  ollama run llama2        # Larger model, better answers"
Write-Host "  ollama run neural-chat   # Conversational model`n"

Write-Host "Step 3: Start the Voice Assistant"
Write-Host "In another PowerShell, navigate to this directory and run:`n"
Write-Host "  .\.venv\Scripts\python.exe app.py`n"

Write-Host "Step 4: Open in browser"
Write-Host "  http://localhost:5000`n"

Write-Host "That's it! Your Voice Assistant is now running with local AI." -ForegroundColor Green
