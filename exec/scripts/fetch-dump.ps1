<#
.SYNOPSIS
  EC2에서 BOMI DB 덤프를 생성하고 로컬로 내려받아 무결성까지 확인한다.

.DESCRIPTION
  1) 원격에서 exec/scripts/dump-db.sh 실행 (덤프 생성 + 복원 검증)
  2) 가장 최근 덤프 파일을 자동으로 찾음 (파일명을 손으로 칠 필요 없음)
  3) scp 로 다운로드
  4) 원격/로컬 SHA256 비교
  5) 덤프 메타 헤더 출력

.EXAMPLE
  # ~/.ssh/config 에 Host bomi 를 등록한 경우 (권장)
  .\fetch-dump.ps1

.EXAMPLE
  # 별칭 없이 직접 지정
  .\fetch-dump.ps1 -Server ubuntu@i15e102.p.ssafy.io -Key C:\keys\bomi.pem

.EXAMPLE
  # 이미 만들어 둔 덤프를 내려받기만 (재생성 안 함)
  .\fetch-dump.ps1 -SkipDump
#>
[CmdletBinding()]
param(
    # SSH 대상. ~/.ssh/config 의 Host 별칭이거나 user@host 형식.
    [string]$Server   = 'bomi',

    # .pem 경로. ~/.ssh/config 에 IdentityFile 을 넣었으면 생략.
    [string]$Key      = '',

    # EC2의 저장소 경로
    [string]$RemoteRepo = '/home/ubuntu/bomi/deploy/source',

    # 로컬 저장 위치
    [string]$Out      = 'C:\BOMI\exec',

    # 덤프 직전 reset-demo.sql 적용 (시연 가능 상태로)
    [switch]$NoReset,

    # 덤프를 새로 만들지 않고 기존 최신본만 내려받는다
    [switch]$SkipDump
)

$ErrorActionPreference = 'Stop'

# ── ssh/scp 공통 인자 ───────────────────────────────────────────────────────
$sshArgs = @()
if ($Key) {
    if (-not (Test-Path $Key)) { throw "키 파일을 찾을 수 없습니다: $Key" }
    $sshArgs += @('-i', $Key)
}

function Invoke-Remote([string]$Command) {
    $output = & ssh @sshArgs $Server $Command 2>&1
    if ($LASTEXITCODE -ne 0) {
        $output | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
        throw "원격 명령 실패 (exit $LASTEXITCODE): $Command"
    }
    return $output
}

Write-Host ''
Write-Host '=== BOMI 덤프 가져오기 ===' -ForegroundColor Cyan
Write-Host "  대상 : $Server"
Write-Host "  경로 : $RemoteRepo"
Write-Host ''

# ── 0. 연결 확인 ────────────────────────────────────────────────────────────
Write-Host '[1/5] SSH 연결 확인...' -ForegroundColor Yellow
$whoami = (Invoke-Remote 'whoami') -join ''
Write-Host "      OK ($whoami)"

# ── 1. 덤프 생성 ────────────────────────────────────────────────────────────
if ($SkipDump) {
    Write-Host '[2/5] 덤프 생성 건너뜀 (-SkipDump)' -ForegroundColor DarkGray
} else {
    $resetFlag = if ($NoReset) { '' } else { '--reset' }
    Write-Host "[2/5] 원격에서 덤프 생성 중 (dump-db.sh $resetFlag)..." -ForegroundColor Yellow
    Write-Host '      ─────────────────────────────────────────' -ForegroundColor DarkGray
    $cmd = "cd '$RemoteRepo' && chmod +x exec/scripts/dump-db.sh && exec/scripts/dump-db.sh $resetFlag"
    Invoke-Remote $cmd | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
    Write-Host '      ─────────────────────────────────────────' -ForegroundColor DarkGray
}

# ── 2. 최신 덤프 파일 찾기 ──────────────────────────────────────────────────
Write-Host '[3/5] 최신 덤프 파일 조회...' -ForegroundColor Yellow
$remoteFile = ((Invoke-Remote "ls -t '$RemoteRepo'/exec/bomi-dump-*.sql 2>/dev/null | head -1") -join '').Trim()
if (-not $remoteFile) {
    throw "덤프 파일을 찾을 수 없습니다. $RemoteRepo/exec/ 를 확인하세요. (Jenkins 워크스페이스에 생성됐을 수 있습니다)"
}
$fileName   = Split-Path $remoteFile -Leaf
$remoteSize = ((Invoke-Remote "stat -c %s '$remoteFile'") -join '').Trim()
Write-Host "      $fileName ($([math]::Round([int64]$remoteSize / 1MB, 2)) MB)"

# ── 3. 다운로드 ─────────────────────────────────────────────────────────────
if (-not (Test-Path $Out)) { New-Item -ItemType Directory -Path $Out -Force | Out-Null }
$localPath = Join-Path $Out $fileName

Write-Host '[4/5] 다운로드 중...' -ForegroundColor Yellow
& scp @sshArgs "${Server}:${remoteFile}" $localPath
if ($LASTEXITCODE -ne 0) { throw "scp 실패 (exit $LASTEXITCODE)" }
Write-Host "      → $localPath"

# ── 4. 무결성 검증 ──────────────────────────────────────────────────────────
Write-Host '[5/5] SHA256 비교...' -ForegroundColor Yellow
$remoteHash = (((Invoke-Remote "sha256sum '$remoteFile'") -join '') -split '\s+')[0]
$localHash  = (Get-FileHash $localPath -Algorithm SHA256).Hash.ToLower()

if ($remoteHash -ne $localHash) {
    Write-Host "      원격 : $remoteHash" -ForegroundColor Red
    Write-Host "      로컬 : $localHash"  -ForegroundColor Red
    throw '해시 불일치 — 전송이 손상되었습니다. 다시 받으세요.'
}
Write-Host "      OK  $localHash"

# ── 5. 헤더 출력 ────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '=== 덤프 메타 정보 ===' -ForegroundColor Cyan
Get-Content $localPath -TotalCount 14 | ForEach-Object { Write-Host "  $_" }

Write-Host ''
Write-Host '✅ 완료' -ForegroundColor Green
Write-Host ''
Write-Host '다음 단계:' -ForegroundColor Cyan
Write-Host "  1. exec/03-database-dump.md 의 '덤프 파일' 항목에 파일명 기입:"
Write-Host "       $fileName" -ForegroundColor White
Write-Host '  2. 01/02/03번 문서의 [머지 후 기입] 3곳에 커밋 SHA 기입'
Write-Host '  3. git add exec/  →  commit  →  push'
Write-Host ''
