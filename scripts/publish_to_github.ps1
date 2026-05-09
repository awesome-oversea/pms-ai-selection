<#
GitHub Publish Script - Simplified Version
#>

param(
    [string]$ConfigFile = ".github-publish.env"
)

# Read configuration
$config = @{}
Get-Content $ConfigFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $parts = $line -split '=', 2
        $config[$parts[0].Trim()] = $parts[1].Trim()
    }
}

$username = $config["GITHUB_USERNAME"]
$token = $config["GITHUB_TOKEN"]
$repoName = $config["REPO_NAME"]

Write-Host "`n[1/5] Configuration loaded" -ForegroundColor Green
Write-Host "      Username: $username"
Write-Host "      Repo Name: $repoName`n"

# Check gh CLI
Write-Host "[2/5] Checking GitHub CLI..." -ForegroundColor Yellow
try {
    gh --version | Out-Null
    Write-Host "      ✓ GitHub CLI installed`n" -ForegroundColor Green
} catch {
    Write-Host "      Installing GitHub CLI..." -ForegroundColor Yellow
    winget install GitHub.cli --silent
    Write-Host "      ✓ GitHub CLI installed`n" -ForegroundColor Green
}

# Login
Write-Host "[3/5] Logging into GitHub..." -ForegroundColor Yellow
$env:GH_TOKEN = $token
echo $token | gh auth login --with-token
Write-Host "      ✓ Login successful`n" -ForegroundColor Green

# Create repo
Write-Host "[4/5] Creating repository..." -ForegroundColor Yellow
try {
    gh repo view "$username/$repoName" | Out-Null
    Write-Host "      Repo exists, skipping creation`n" -ForegroundColor Yellow
} catch {
    gh repo create "$repoName" --public --description "AI product selection system"
    Write-Host "      ✓ Repo created successfully`n" -ForegroundColor Green
}

# Push code
Write-Host "[5/5] Pushing code..." -ForegroundColor Yellow
$remoteUrl = "https://$username`:$token@github.com/$username/$repoName.git"
git remote add origin $remoteUrl 2>&1 | Out-Null
git remote set-url origin $remoteUrl 2>&1 | Out-Null
git add .
git commit -m "Initial commit - AI product selection system" 2>&1 | Out-Null
git branch -M main
git push -u origin main

Write-Host "      ✓ Code pushed successfully`n" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "         Publish completed!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Repo URL: https://github.com/$username/$repoName`n"