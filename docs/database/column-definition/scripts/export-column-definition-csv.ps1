[CmdletBinding()]
param(
    [string]$Workbook = '',
    [string]$OutputDir = '',
    [switch]$Check
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($Workbook)) { $Workbook = Join-Path $scriptDirectory '..\BOMI_컬럼정의서.xlsx' }
if ([string]::IsNullOrWhiteSpace($OutputDir)) { $OutputDir = Join-Path $scriptDirectory '..\snapshots' }
$Workbook = [System.IO.Path]::GetFullPath($Workbook)
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
$mainNs = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
$relNs = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

function Get-ZipText([System.IO.Compression.ZipArchive]$Archive, [string]$Name) {
    $entry = $Archive.GetEntry($Name)
    if ($null -eq $entry) { return $null }
    $stream = $entry.Open()
    try {
        $reader = [System.IO.StreamReader]::new($stream, [System.Text.Encoding]::UTF8, $true)
        try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
    } finally { $stream.Dispose() }
}

function Get-ColumnIndex([string]$CellReference) {
    $letters = [regex]::Match($CellReference, '^[A-Z]+').Value
    $value = 0
    foreach ($char in $letters.ToCharArray()) { $value = $value * 26 + ([int]$char - 64) }
    return $value - 1
}

function Get-CellValue($Cell, [System.Collections.Generic.List[string]]$SharedStrings, $NamespaceManager) {
    $type = $Cell.GetAttribute('t')
    if ($type -eq 'inlineStr') {
        $texts = $Cell.SelectNodes('.//m:t', $NamespaceManager)
        return (($texts | ForEach-Object { $_.'#text' }) -join '')
    }
    $valueNode = $Cell.SelectSingleNode('./m:v', $NamespaceManager)
    $raw = if ($null -eq $valueNode) { '' } else { [string]$valueNode.InnerText }
    if ($type -eq 's' -and $raw -ne '') { return $SharedStrings[[int]$raw] }
    if ($type -eq 'b') { return $(if ($raw -eq '1') { 'TRUE' } else { 'FALSE' }) }
    return $raw
}

function Get-WorkbookRows([string]$Path) {
    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $shared = [System.Collections.Generic.List[string]]::new()
        $sharedText = Get-ZipText $archive 'xl/sharedStrings.xml'
        if ($null -ne $sharedText) {
            [xml]$sharedXml = $sharedText
            $sharedNs = [System.Xml.XmlNamespaceManager]::new($sharedXml.NameTable)
            $sharedNs.AddNamespace('m', $mainNs)
            foreach ($item in $sharedXml.SelectNodes('//m:si', $sharedNs)) {
                $text = (($item.SelectNodes('.//m:t', $sharedNs) | ForEach-Object { $_.'#text' }) -join '')
                $shared.Add([string]$text)
            }
        }

        [xml]$workbookXml = Get-ZipText $archive 'xl/workbook.xml'
        [xml]$relsXml = Get-ZipText $archive 'xl/_rels/workbook.xml.rels'
        $workbookNs = [System.Xml.XmlNamespaceManager]::new($workbookXml.NameTable)
        $workbookNs.AddNamespace('m', $mainNs)
        $workbookNs.AddNamespace('r', $relNs)
        $targets = @{}
        foreach ($relationship in $relsXml.SelectNodes('//*[local-name()="Relationship"]')) {
            $targets[$relationship.Id] = [string]$relationship.Target
        }

        $result = [ordered]@{}
        foreach ($sheet in $workbookXml.SelectNodes('//m:sheets/m:sheet', $workbookNs)) {
            $relationId = $sheet.GetAttribute('id', $relNs)
            $target = $targets[$relationId].Replace('\', '/')
            if ($target.StartsWith('/')) { $target = $target.TrimStart('/') }
            elseif (-not $target.StartsWith('xl/')) { $target = 'xl/' + $target }
            [xml]$sheetXml = Get-ZipText $archive $target
            $sheetNs = [System.Xml.XmlNamespaceManager]::new($sheetXml.NameTable)
            $sheetNs.AddNamespace('m', $mainNs)
            $sheetRows = [System.Collections.Generic.List[object]]::new()
            foreach ($row in $sheetXml.SelectNodes('//m:sheetData/m:row', $sheetNs)) {
                $values = [System.Collections.Generic.List[string]]::new()
                foreach ($cell in $row.SelectNodes('./m:c', $sheetNs)) {
                    $index = Get-ColumnIndex $cell.r
                    while ($values.Count -le $index) { $values.Add('') }
                    $values[$index] = [string](Get-CellValue $cell $shared $sheetNs)
                }
                while ($values.Count -gt 0 -and $values[$values.Count - 1] -eq '') { $values.RemoveAt($values.Count - 1) }
                $sheetRows.Add($values.ToArray())
            }
            $result[[string]$sheet.name] = $sheetRows.ToArray()
        }
        return $result
    } finally { $archive.Dispose() }
}

function Get-Table($Rows, [string]$FirstHeader) {
    $headerIndex = -1
    for ($i = 0; $i -lt $Rows.Count; $i++) {
        if ($Rows[$i].Count -gt 0 -and $Rows[$i][0] -eq $FirstHeader) { $headerIndex = $i; break }
    }
    if ($headerIndex -lt 0) { throw "표 머리글을 찾지 못했습니다: $FirstHeader" }
    $headers = [System.Collections.Generic.List[string]]::new()
    foreach ($value in $Rows[$headerIndex]) { $headers.Add([string]$value) }
    while ($headers.Count -gt 0 -and $headers[$headers.Count - 1] -eq '') { $headers.RemoveAt($headers.Count - 1) }
    $data = [System.Collections.Generic.List[object]]::new()
    for ($i = $headerIndex + 1; $i -lt $Rows.Count; $i++) {
        $row = [string[]]::new($headers.Count)
        $populated = $false
        for ($j = 0; $j -lt $headers.Count; $j++) {
            $row[$j] = if ($j -lt $Rows[$i].Count) { [string]$Rows[$i][$j] } else { '' }
            if ($row[$j] -ne '') { $populated = $true }
        }
        if (-not $populated) { break }
        $data.Add($row)
    }
    return @{ Headers = $headers.ToArray(); Rows = $data.ToArray() }
}

function ConvertTo-CsvField([string]$Value) {
    if ($null -eq $Value) { $Value = '' }
    if ($Value.IndexOfAny([char[]]",`"`r`n") -ge 0) { return '"' + $Value.Replace('"', '""') + '"' }
    return $Value
}

function ConvertTo-CsvBytes([string[]]$Headers, $Rows) {
    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add((($Headers | ForEach-Object { ConvertTo-CsvField $_ }) -join ','))
    foreach ($row in $Rows) { $lines.Add((($row | ForEach-Object { ConvertTo-CsvField $_ }) -join ',')) }
    $body = ($lines -join "`r`n") + "`r`n"
    $encoding = [System.Text.UTF8Encoding]::new($true)
    $preamble = $encoding.GetPreamble()
    $content = $encoding.GetBytes($body)
    $result = [byte[]]::new($preamble.Length + $content.Length)
    [Array]::Copy($preamble, 0, $result, 0, $preamble.Length)
    [Array]::Copy($content, 0, $result, $preamble.Length, $content.Length)
    return $result
}

function Test-ByteArrayEqual([byte[]]$Left, [byte[]]$Right) {
    if ($Left.Length -ne $Right.Length) { return $false }
    for ($index = 0; $index -lt $Left.Length; $index++) {
        if ($Left[$index] -ne $Right[$index]) { return $false }
    }
    return $true
}

function Get-OrdinalSortKey([string]$Value) {
    return (($Value.ToCharArray() | ForEach-Object { '{0:X6}' -f [int]$_ }) -join '')
}

$snapshotMap = [ordered]@{
    'tables.csv' = @('03_테이블정의', '테이블 ID')
    'columns.csv' = @('04_컬럼정의', '컬럼 ID')
    'constraints.csv' = @('05_관계_제약조건', '제약조건 ID')
    'indexes.csv' = @('06_인덱스정의', '인덱스 ID')
    'jsonb-fields.csv' = @('07_JSONB정의', 'JSONB 구조 ID')
    'vector-fields.csv' = @('08_벡터정의', '벡터 정의 ID')
    'code-values.csv' = @('09_코드정의', '코드 그룹 ID')
    'interface-mappings.csv' = @('10_연계매핑', '매핑 ID')
    'change-history.csv' = @('11_변경이력', '문서 버전')
}

$sheets = Get-WorkbookRows $Workbook
$mismatches = [System.Collections.Generic.List[string]]::new()
$tableOrder = @{
    'app_user'=0
    'care_relationship'=1
    'robot'=2
    'onboarding_session'=3
    'onboarding_answer'=4
    'scenario'=5
    'conversation'=6
    'memory'=7
    'care_record'=8
    'audit_log'=9
}

foreach ($snapshot in $snapshotMap.GetEnumerator()) {
    $sheetName, $firstHeader = $snapshot.Value
    if (-not $sheets.Contains($sheetName)) { throw "필수 시트가 없습니다: $sheetName" }
    $table = Get-Table $sheets[$sheetName] $firstHeader
    $keep = 0..($table.Headers.Count - 1) | Where-Object { $table.Headers[$_] -notin @('관련 객체 이동', '가이드 이동', '오류 링크') }
    $headers = [string[]]($keep | ForEach-Object { $table.Headers[$_] })
    $rows = @($table.Rows | ForEach-Object { $source = $_; ,([string[]]($keep | ForEach-Object { $source[$_] })) })

    if ($firstHeader -eq '컬럼 ID') {
        $tableIndex = [Array]::IndexOf($headers, '테이블 물리명')
        $sequenceIndex = [Array]::IndexOf($headers, '컬럼 순번')
        $rows = @($rows | Sort-Object @{Expression={$tableOrder[$_[$tableIndex]]}}, @{Expression={[int][double]$_[$sequenceIndex]}})
    } elseif ($firstHeader -eq 'JSONB 구조 ID') {
        $pathIndex = [Array]::IndexOf($headers, 'JSON 경로')
        $rows = @($rows | Sort-Object @{Expression={Get-OrdinalSortKey $_[0]}}, @{Expression={Get-OrdinalSortKey $_[$pathIndex]}})
    } elseif ($firstHeader -eq '코드 그룹 ID') {
        $orderIndex = [Array]::IndexOf($headers, '표시 순서')
        $rows = @($rows | Sort-Object @{Expression={Get-OrdinalSortKey $_[0]}}, @{Expression={[int][double]$_[$orderIndex]}})
    } elseif ($firstHeader -eq '문서 버전') {
        $dateIndex = [Array]::IndexOf($headers, '변경일')
        $targetIndex = [Array]::IndexOf($headers, '대상 ID')
        $rows = @($rows | Sort-Object @{Expression={Get-OrdinalSortKey $_[0]}}, @{Expression={Get-OrdinalSortKey $_[$dateIndex]}}, @{Expression={Get-OrdinalSortKey $_[$targetIndex]}})
    } else {
        $rows = @($rows | Sort-Object @{Expression={Get-OrdinalSortKey $_[0]}})
    }

    $bytes = ConvertTo-CsvBytes $headers $rows
    $target = Join-Path $OutputDir $snapshot.Key
    if ($Check) {
        if (-not (Test-Path -LiteralPath $target) -or -not (Test-ByteArrayEqual ([System.IO.File]::ReadAllBytes($target)) $bytes)) { $mismatches.Add($snapshot.Key) }
    } else {
        [System.IO.Directory]::CreateDirectory($OutputDir) | Out-Null
        [System.IO.File]::WriteAllBytes($target, $bytes)
    }
}

if ($Check -and $mismatches.Count -gt 0) {
    Write-Error ('Excel과 일치하지 않는 CSV: ' + ($mismatches -join ', '))
    exit 1
}
$action = if ($Check) { '검증' } else { '생성' }
Write-Output "CSV 스냅샷 9개 $action 완료"
