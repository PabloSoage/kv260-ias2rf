<#
.SYNOPSIS
    Compile, elaborate, and run a Verilog testbench in Vivado XSim (batch mode).

.DESCRIPTION
    Runs xvlog, xelab (with unisims_ver, secureip, and glbl), and xsim -R inside
    an isolated work directory under fpga/sim/out/work_<runName>, writing the full
    combined log to fpga/sim/out/<runName>.log.

    Exits 0 only if the simulation output contains a line matching ^PASS\b and
    no line matching ^FAIL\b.

.EXAMPLE
    .\fpga\sim\run.ps1 tb_serdes7
    .\fpga\sim\run.ps1 tb_serdes7 -Mutate flip_bit
#>
param(
    [Parameter(Mandatory = $true, Position = 0)][string]$Bench,
    [string]$Mutate = '',
    [string[]]$Define = @(),
    [string]$Vivado = 'D:\AMDDesignTools\2026.1\Vivado'
)

$ErrorActionPreference = 'Stop'

$simDir   = $PSScriptRoot
$fpgaDir  = Split-Path -Parent $simDir
$outDir   = Join-Path $simDir 'out'
$binDir   = Join-Path $Vivado 'bin'
$glblPath = Join-Path $Vivado 'data\verilog\src\glbl.v'

$benchFile = Join-Path $simDir "$Bench.v"
if (-not (Test-Path $benchFile)) {
    throw "Testbench not found: $benchFile"
}
if (-not (Test-Path $glblPath)) {
    throw "Vivado glbl.v not found: $glblPath"
}

$defSuffix = ''
if ($Define -and ($Define.Count -gt 0)) {
    $cleanDefs = @($Define | Where-Object { $_ } | ForEach-Object { $_ -replace '[^A-Za-z0-9_]', '_' })
    if ($cleanDefs.Count -gt 0) {
        $defSuffix = '-def-' + ($cleanDefs -join '_')
    }
}
$mutSuffix = if ($Mutate) { "-mutate-$Mutate" } else { '' }
$runName = "$Bench$defSuffix$mutSuffix"
$workDir = Join-Path $outDir "work_$runName"
$logFile = Join-Path $outDir "$runName.log"

if (Test-Path $workDir) {
    Remove-Item -Recurse -Force $workDir
}
New-Item -ItemType Directory -Force $outDir, $workDir | Out-Null

$xvlogArgs = @('--incr')
foreach ($d in $Define) {
    if ($d) { $xvlogArgs += @('-d', $d) }
}
if ($Mutate) {
    $mutMacro = 'MUTATE_' + ($Mutate.ToUpperInvariant() -replace '[^A-Z0-9_]', '_')
    $xvlogArgs += @('-d', $mutMacro)
}

# Include any shared RTL files under fpga/{third_party,link,artix,kria} if present.
$rtlFiles = @()
foreach ($sub in @('third_party', 'link', 'artix', 'kria')) {
    $dir = Join-Path $fpgaDir $sub
    if (Test-Path $dir) {
        $rtlFiles += Get-ChildItem $dir -Recurse -Include *.v, *.sv | ForEach-Object { $_.FullName }
    }
}

$xvlogArgs += @($glblPath) + $rtlFiles + @($benchFile)

$logLines = New-Object System.Collections.Generic.List[string]
$logLines.Add("=== run.ps1: bench=$Bench run=$runName date=$(Get-Date -Format o) ===")
$logLines.Add("=== vivado=$Vivado ===")

$xsimLines = @()
$toolFailed = $false

Push-Location $workDir
try {
    $logLines.Add("--- xvlog ---")
    $xvlogOut = & (Join-Path $binDir 'xvlog.bat') @xvlogArgs 2>&1 | ForEach-Object { $_.ToString() }
    $xvlogEc = $LASTEXITCODE
    foreach ($ln in $xvlogOut) { $logLines.Add($ln) }
    if ($xvlogEc -ne 0) {
        $logLines.Add("ERROR: xvlog exited with code $xvlogEc")
        $toolFailed = $true
    }

    if (-not $toolFailed) {
        $logLines.Add("--- xelab ---")
        $xelabArgs = @(
            '--timescale', '1ns/1ps',
            '-debug', 'off',
            '-L', 'unisims_ver',
            '-L', 'secureip',
            $Bench, 'glbl',
            '-s', 'sim'
        )
        $xelabOut = & (Join-Path $binDir 'xelab.bat') @xelabArgs 2>&1 | ForEach-Object { $_.ToString() }
        $xelabEc = $LASTEXITCODE
        foreach ($ln in $xelabOut) { $logLines.Add($ln) }
        if ($xelabEc -ne 0) {
            $logLines.Add("ERROR: xelab exited with code $xelabEc")
            $toolFailed = $true
        }
    }

    if (-not $toolFailed) {
        $logLines.Add("--- xsim ---")
        $t0 = Get-Date
        $xsimLines = & (Join-Path $binDir 'xsim.bat') 'sim' '-R' 2>&1 | ForEach-Object { $_.ToString() }
        $xsimEc = $LASTEXITCODE
        $secs = [Math]::Round(((Get-Date) - $t0).TotalSeconds, 2)
        foreach ($ln in $xsimLines) { $logLines.Add($ln) }
        $logLines.Add("=== xsim_exit=$xsimEc elapsed_s=$secs ===")
        if ($xsimEc -ne 0) {
            $logLines.Add("ERROR: xsim exited with code $xsimEc")
            $toolFailed = $true
        }
    }
} finally {
    Pop-Location
}

$logLines | Out-File -FilePath $logFile -Encoding utf8

$passMatch = $xsimLines | Select-String -Pattern '^PASS\b' | Select-Object -First 1
$failMatch = $xsimLines | Select-String -Pattern '^FAIL\b' | Select-Object -First 1

Write-Output "Log: $logFile"
if ($toolFailed) {
    Write-Output "FAIL: tool error (see $logFile)"
    exit 1
}
if ($failMatch) {
    Write-Output $failMatch.Line
    exit 1
}
if ($passMatch) {
    Write-Output $passMatch.Line
    exit 0
}

Write-Output "FAIL: no PASS/FAIL summary line printed by $Bench (see $logFile)"
exit 1
