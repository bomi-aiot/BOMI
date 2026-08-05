$ErrorActionPreference = 'Stop'
$src = 'C:\Users\SSAFY\Downloads\자율PJT_해피너스_최종발표피피티자료.pdf'
$out = 'C:\BOMI\tmp\happynurse_ref'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$app = New-Object -ComObject AcroExch.App
$av = New-Object -ComObject AcroExch.AVDoc
if (-not $av.Open($src, '')) { throw 'PDF open failed' }
$pd = $av.GetPDDoc()
$pages = $pd.GetNumPages()
Write-Output "pages=$pages"
$jso = $pd.GetJSObject()
$target = ($out + '\reference.jpeg').Replace('\', '/')
$jso.saveAs($target, 'com.adobe.acrobat.jpeg')
$av.Close($true)
$app.Exit()
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($jso) | Out-Null
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($pd) | Out-Null
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($av) | Out-Null
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
Get-ChildItem -LiteralPath $out | Select-Object -First 5 Name,Length
