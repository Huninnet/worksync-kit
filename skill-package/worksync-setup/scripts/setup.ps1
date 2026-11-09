# WorkSync 一键接管 + 环境自检
# 用法: powershell -ExecutionPolicy Bypass -File "$env:OneDrive\WorkBuddySync\_tool\setup.ps1"
$ErrorActionPreference = "Stop"
$script:log = New-Object System.Collections.Generic.List[string]
$script:od = $null

function Note($m) { $script:log.Add($m); Write-Host $m }
function Good($m) { $script:log.Add("[OK] $m"); Write-Host "  [OK] $m" -ForegroundColor Green }
function Bad($m)  { $script:log.Add("[X ] $m"); Write-Host "  [X ] $m" -ForegroundColor Red }

try {
    Note ""
    Note "=== WorkSync 一键接管 · $(Get-Date -Format 'yyyy-MM-dd HH:mm') · $env:COMPUTERNAME ==="

    Note "[1/5] 检查 OneDrive ..."
    $od = $env:OneDrive
    if (-not $od -or -not (Test-Path $od)) {
        foreach ($c in @("$env:USERPROFILE\OneDrive", "D:\OneDrive", "$env:USERPROFILE\OneDrive - 个人")) {
            if (Test-Path $c) { $od = $c; break }
        }
    }
    $script:od = $od
    if (-not $od) {
        throw "找不到 OneDrive 目录 —— OneDrive 客户端可能没有登录。请先登录 OneDrive，再重跑本脚本。"
    }
    Good "OneDrive 根目录: $od"

    Note "[2/5] 检查云端工具是否已同步到这台机器 ..."
    $src = Join-Path $od "WorkBuddySync\_tool"
    if (-not (Test-Path (Join-Path $src "sync.py"))) {
        throw "云端还没把 _tool\sync.py 同步过来。请在资源管理器打开这个文件夹、等它下载完，再重跑: $src"
    }
    Good "工具齐全: $src"

    Note "[3/5] 复制工具到本地 ..."
    $dst = Join-Path $env:USERPROFILE "WorkBuddy\WorkSync"
    New-Item -ItemType Directory -Force $dst | Out-Null
    foreach ($f in "sync.py", "config.json", "install.ps1", "setup.ps1", "README.md") {
        Copy-Item (Join-Path $src $f) $dst -Force
    }
    Good "已复制到 $dst"

    Note "[4/5] 查找 Python ..."
    $cands = @()
    $cands += (Join-Path $env:USERPROFILE ".workbuddy\binaries\python\versions\3.13.12\python.exe")
    $c1 = (Get-Command python -ErrorAction SilentlyContinue).Source
    if ($c1) { $cands += $c1 }
    $c2 = (Get-Command py -ErrorAction SilentlyContinue).Source
    if ($c2) { $cands += $c2 }
    $py = $null
    foreach ($c in $cands) {
        if (-not (Test-Path $c)) { continue }
        & $c -c "print(1)" *> $null
        if ($LASTEXITCODE -eq 0) { $py = $c; break }
    }
    if (-not $py) {
        throw "找不到可用的 Python。请先安装 WorkBuddy 并登录，或手动把 Python 路径告诉我。"
    }
    Good "Python: $py"

    Note "[5/5] 拉取云端内容 + 打印交接简报 ..."
    & $py (Join-Path $dst "sync.py") pull
    if ($LASTEXITCODE -ne 0) { throw "sync.py pull 失败，退出码 $LASTEXITCODE" }
    & $py (Join-Path $dst "sync.py") resume
    if ($LASTEXITCODE -ne 0) { throw "sync.py resume 失败，退出码 $LASTEXITCODE" }

    Note ""
    Note "全部完成。接下来: 执行 install.ps1 注册自动同步，然后回 WorkBuddy 跟辰说「接班」。"
}
catch {
    $msg = "失败: $($_.Exception.Message)"
    Bad $msg
    $script:log.Add($msg)
    try {
        if ($script:od) {
            $logPath = Join-Path $script:od "WorkBuddySync\_tool\setup-error.log"
            $header = "==== setup 失败 · $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') · $env:COMPUTERNAME ===="
            Add-Content -Path $logPath -Value ($header + "`r`n" + ($script:log -join "`r`n")) -Encoding UTF8
            Write-Host "错误详情已写入 $logPath （辰在家里也能看到，不用复制）" -ForegroundColor Yellow
        }
    } catch {}
    exit 1
}
