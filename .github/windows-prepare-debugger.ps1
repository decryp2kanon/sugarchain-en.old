# Resolve the x64 Microsoft debugger on a disposable GitHub-hosted Windows runner.
$ErrorActionPreference = 'Stop'
if ($env:GITHUB_ACTIONS -ne 'true' -or $env:RUNNER_ENVIRONMENT -ne 'github-hosted' -or $env:RUNNER_OS -ne 'Windows') {
    throw 'This preparation requires a GitHub-hosted Windows QA runner.'
}

function Test-MicrosoftFile([string]$Path) {
    $signature = Get-AuthenticodeSignature -FilePath $Path
    return $signature.Status -eq 'Valid' -and $null -ne $signature.SignerCertificate -and
        $signature.SignerCertificate.Subject -match '(?:^|,\s*)O=Microsoft Corporation(?:,|$)'
}

function Test-Amd64Cdb([string]$Path) {
    if (!(Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $engine = Join-Path (Split-Path -Parent $Path) 'dbgeng.dll'
    if (!(Test-Path -LiteralPath $engine -PathType Leaf)) { return $false }
    $reader = [IO.BinaryReader]::new([IO.File]::OpenRead($Path))
    try {
        if ($reader.ReadUInt16() -ne 0x5a4d) { return $false }
        $reader.BaseStream.Position = 0x3c
        $offset = $reader.ReadUInt32()
        if ($offset -gt $reader.BaseStream.Length - 6) { return $false }
        $reader.BaseStream.Position = $offset
        if ($reader.ReadUInt32() -ne 0x4550 -or $reader.ReadUInt16() -ne 0x8664) { return $false }
    } finally {
        $reader.Dispose()
    }
    return (Test-MicrosoftFile $Path) -and (Test-MicrosoftFile $engine)
}

function Get-ExistingCdb {
    $roots = @($env:WindowsSdkDir, (Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10'))
    foreach ($key in @('HKLM:\SOFTWARE\Microsoft\Windows Kits\Installed Roots', 'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows Kits\Installed Roots')) {
        $roots += (Get-ItemProperty -LiteralPath $key -Name KitsRoot10 -ErrorAction SilentlyContinue).KitsRoot10
    }
    foreach ($root in ($roots | Where-Object { $_ } | Select-Object -Unique)) {
        foreach ($relative in @('Debuggers\x64\cdb.exe', 'Debuggers\10.*\x64\cdb.exe', 'bin\10.*\x64\cdb.exe')) {
            foreach ($item in @(Get-Item -Path (Join-Path $root $relative) -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)) {
                if (Test-Amd64Cdb $item.FullName) { return $item.FullName }
            }
        }
    }
    $cmd = Get-Command cdb.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd -and (Test-Amd64Cdb $cmd.Source)) { return $cmd.Source }
}

$private = Join-Path $env:RUNNER_TEMP ('en-qa-cdb-' + [Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $private
try {
    $cdb = Get-ExistingCdb
    $source = 'installed SDK'
    if (!$cdb) {
        $source = 'Windows SDK 10.0.26100.1742 signed x64 administrative image'
        $uri = 'https://download.microsoft.com/download/e/b/3/eb320eb1-b21e-4e6e-899e-d6aec552ecb0/KIT_BUNDLE_WINDOWSSDK_MEDIACREATION/Installers/X64%20Debuggers%20And%20Tools-x64_en-us.msi'
        $msi = Join-Path $private 'debuggers.msi'
        Invoke-WebRequest -Uri $uri -OutFile $msi
        $wanted = '81210584AB6423560E15756F291F5B5C67DBAD49E9B2F3453E6A6B6817BEF67B'
        if ((Get-FileHash -LiteralPath $msi -Algorithm SHA256).Hash -ne $wanted -or !(Test-MicrosoftFile $msi)) {
            throw 'The Microsoft x64 debugger package failed its SHA-256 or Authenticode check.'
        }
        $image = Join-Path $private 'sdk'
        $null = New-Item -ItemType Directory -Path $image
        $argsMsi = '/a "{0}" /qn /norestart TARGETDIR="{1}"' -f $msi, $image
        $extraction = Start-Process -FilePath "$env:SystemRoot\System32\msiexec.exe" -ArgumentList $argsMsi -Wait -PassThru
        if ($extraction.ExitCode -ne 0) { throw "The debugger administrative extraction returned $($extraction.ExitCode)." }
        foreach ($file in @(Get-ChildItem -LiteralPath $image -Filter cdb.exe -Recurse -File)) {
            if (Test-Amd64Cdb $file.FullName) {
                $engine = Join-Path $file.DirectoryName 'dbgeng.dll'
                if ((Get-FileHash -LiteralPath $file.FullName).Hash -ne 'E8F8E9DCF084262A948D3E324CAA0555D189F962D8969333645673333CF00AF5' -or
                    (Get-FileHash -LiteralPath $engine).Hash -ne '5AFBFB630E8875AAAD9D146F67770C9450445C91A7BED7A015509036550778F7') {
                    throw 'The extracted x64 debugger files differ from the original Microsoft SDK.'
                }
                $cdb = $file.FullName
                break
            }
        }
    }
    if (!$cdb) { throw 'The Windows SDK did not provide a verifiable AMD64 CDB and side-by-side dbgeng.dll.' }
    "EN_QT_CDB=$cdb" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
    "EN_QT_CDB_PRIVATE=$private" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
    $file = Get-Item -LiteralPath $cdb
    Write-Output "Verified AMD64 CDB from $source. Version $($file.VersionInfo.FileVersion), SHA-256 $((Get-FileHash -LiteralPath $cdb -Algorithm SHA256).Hash)."
} catch {
    Remove-Item -LiteralPath $private -Recurse -Force
    throw
}
