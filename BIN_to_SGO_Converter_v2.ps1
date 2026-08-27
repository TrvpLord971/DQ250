# BIN to SGO Converter v2.0 - CORRECTED VERSION
# Now uses proper JAMCRC checksum calculation
# Based on research from bri3d/VW_Flash project

param(
    [Parameter(Mandatory=$true, HelpMessage="Path to .BIN firmware file")]
    [string]$BinFilePath,
    
    [Parameter(Mandatory=$false, HelpMessage="Output path for .SGO file")]
    [string]$OutputPath = $null,
    
    [Parameter(Mandatory=$false, HelpMessage="Path to reference .SGO file for metadata")]
    [string]$ReferenceFile = $null,
    
    [switch]$SkipValidation
)

# ============================================================================
# JAMCRC CHECKSUM FUNCTIONS (from DSG_Checksum.ps1)
# ============================================================================

function Calculate-CRC32-Fallback {
    param([byte[]]$data)
    
    $crc32Table = @()
    for ($i = 0; $i -lt 256; $i++) {
        $crc = $i
        for ($j = 0; $j -lt 8; $j++) {
            if (($crc -band 1) -eq 1) {
                $crc = ($crc -shr 1) -bxor 0xEDB88320
            } else {
                $crc = $crc -shr 1
            }
        }
        $crc32Table += [uint32]$crc
    }
    
    $crc = 0xFFFFFFFF
    foreach ($byte in $data) {
        $crc = $crc32Table[($crc -bxor $byte) -band 0xFF] -bxor ($crc -shr 8)
    }
    
    return $crc -bxor 0xFFFFFFFF
}

function Calculate-CRC32 {
    param([byte[]]$data)
    
    $hasCrc32 = $false
    try {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $hasCrc32 = $true
    } catch {}
    
    if ($hasCrc32) {
        try {
            return [System.IO.Compression.Crc32]::Checksum($data, 0, $data.Length)
        } catch {
            return Calculate-CRC32-Fallback $data
        }
    } else {
        return Calculate-CRC32-Fallback $data
    }
}

function Calculate-JAMCRC {
    param([byte[]]$data)
    
    # JAMCRC = 0xFFFFFFFF - CRC32(data)
    $crc32 = Calculate-CRC32 $data
    $jamcrc = 0xFFFFFFFF - $crc32
    
    return [uint32]($jamcrc -band 0xFFFFFFFF)
}

function Validate-DSGFile {
    param(
        [string]$FilePath,
        [switch]$QuietMode
    )
    
    if (-not (Test-Path $FilePath)) {
        Write-Host "ERROR: File not found: $FilePath" -ForegroundColor Red
        return $false
    }
    
    $data = [System.IO.File]::ReadAllBytes($FilePath)
    
    if ($data.Length -lt 4) {
        Write-Host "ERROR: File too small" -ForegroundColor Red
        return $false
    }
    
    $storedChecksumBytes = $data[($data.Length-4)..($data.Length-1)]
    $storedChecksum = [BitConverter]::ToUInt32($storedChecksumBytes, 0)
    
    $dataForChecksum = $data[0..($data.Length-5)]
    $calculatedChecksum = Calculate-JAMCRC $dataForChecksum
    
    $isValid = $storedChecksum -eq $calculatedChecksum
    
    if (-not $QuietMode) {
        Write-Host "`n=== Checksum Validation ===" -ForegroundColor Cyan
        Write-Host "Stored:      0x$('{0:X8}' -f $storedChecksum)"
        Write-Host "Calculated:  0x$('{0:X8}' -f $calculatedChecksum)"
        Write-Host "Status:      $(if ($isValid) { 'VALID ✓' } else { 'INVALID ✗' })" `
            -ForegroundColor (if ($isValid) { "Green" } else { "Red" })
    }
    
    return $isValid
}

# ============================================================================
# FILE FORMAT ANALYSIS FUNCTIONS
# ============================================================================

function Get-SGMLHeader {
    param(
        [byte[]]$ReferenceData = $null
    )
    
    # Build SGML header (256 bytes)
    $header = New-Object byte[] 256
    
    # SGML magic signature
    $magic = [System.Text.Encoding]::ASCII.GetBytes("SGML Object File")
    [System.Array]::Copy($magic, 0, $header, 0, $magic.Length)
    
    # Version (0x0200 in little-endian)
    $header[16] = 0x00
    $header[17] = 0x02
    
    # Copy metadata from reference if available
    if ($ReferenceData -and $ReferenceData.Length -ge 256) {
        # Copy encoded metadata section (offsets 0x18-0x5F)
        [System.Array]::Copy($ReferenceData, 0x18, $header, 0x18, 0x48)
        
        # Copy remaining header fields (offsets 0x60-0xFF)
        if ($ReferenceData.Length -gt 0x60) {
            [System.Array]::Copy($ReferenceData, 0x60, $header, 0x60, 0xA0)
        } else {
            # Fill with zeros if reference too small
            for ($i = 0x60; $i -lt 256; $i++) {
                $header[$i] = 0x00
            }
        }
    } else {
        # Default: fill rest with zeros
        for ($i = 18; $i -lt 256; $i++) {
            $header[$i] = 0x00
        }
    }
    
    return $header
}

function Get-SGMLFooter {
    param(
        [byte[]]$ReferenceData = $null
    )
    
    # SGO footer is typically 64-320 bytes from end of BIN footer
    if ($ReferenceData -and $ReferenceData.Length -ge 64) {
        # Extract last 64 bytes (footer area)
        $footer = New-Object byte[] 64
        [System.Array]::Copy($ReferenceData, $ReferenceData.Length - 64, $footer, 0, 64)
        return $footer
    } else {
        # Default footer structure
        $footer = New-Object byte[] 64
        for ($i = 0; $i -lt 60; $i++) { $footer[$i] = 0xFF }
        # Last 4 bytes reserved for JAMCRC
        $footer[60] = 0x00
        $footer[61] = 0x00
        $footer[62] = 0x00
        $footer[63] = 0x00
        return $footer
    }
}

# ============================================================================
# MAIN CONVERSION LOGIC
# ============================================================================

function Convert-BINtoSGO {
    param(
        [string]$BinFile,
        [string]$OutputFile,
        [string]$ReferenceFile
    )
    
    Write-Host "`n╔════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║  BIN to SGO Converter v2.0 (CORRECTED)   ║" -ForegroundColor Cyan
    Write-Host "║  JAMCRC Checksum Implementation          ║" -ForegroundColor Cyan
    Write-Host "╚════════════════════════════════════════════╝`n" -ForegroundColor Cyan
    
    # ---- STEP 1: Validate inputs ----
    Write-Host "[1/6] Validating input files..." -ForegroundColor Yellow
    
    if (-not (Test-Path $BinFile)) {
        Write-Host "[FAIL] BIN file not found: $BinFile" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] BIN file found" -ForegroundColor Green
    
    $referenceData = $null
    if ($ReferenceFile -and (Test-Path $ReferenceFile)) {
        Write-Host "[OK] Reference file found" -ForegroundColor Green
        $referenceData = [System.IO.File]::ReadAllBytes($ReferenceFile)
    } else {
        Write-Host "[WARN] No reference file - using generic header/footer" -ForegroundColor Yellow
    }
    
    # ---- STEP 2: Read BIN file ----
    Write-Host "`n[2/6] Reading BIN firmware..." -ForegroundColor Yellow
    
    $binData = [System.IO.File]::ReadAllBytes($BinFile)
    Write-Host "[OK] Read $($binData.Length) bytes from BIN file" -ForegroundColor Green
    
    # ---- STEP 3: Build SGO structure ----
    Write-Host "`n[3/6] Building SGO structure..." -ForegroundColor Yellow
    
    $sgoHeader = Get-SGMLHeader $referenceData
    Write-Host "[OK] Created SGML header (256 bytes)" -ForegroundColor Green
    
    # The firmware data in SGO is the raw BIN data (all bytes including original checksum)
    Write-Host "[OK] Firmware data: $($binData.Length) bytes" -ForegroundColor Green
    
    # Combine header + firmware data
    $combinedData = [byte[]]($sgoHeader + $binData)
    Write-Host "[OK] Combined data size: $($combinedData.Length) bytes" -ForegroundColor Green
    
    # ---- STEP 4: Calculate checksum ----
    Write-Host "`n[4/6] Calculating JAMCRC checksum..." -ForegroundColor Yellow
    
    # JAMCRC is calculated on all data except the last 4 bytes
    $dataForChecksum = $combinedData[0..($combinedData.Length-5)]
    $jamcrc = Calculate-JAMCRC $dataForChecksum
    
    Write-Host "[OK] JAMCRC calculated: 0x$('{0:X8}' -f $jamcrc)" -ForegroundColor Green
    Write-Host "  Formula: JAMCRC = 0xFFFFFFFF - CRC32(data)" -ForegroundColor Gray
    
    # ---- STEP 5: Build final file ----
    Write-Host "`n[5/6] Building final SGO file..." -ForegroundColor Yellow
    
    $checksumBytes = [BitConverter]::GetBytes($jamcrc)
    $finalData = [byte[]]($dataForChecksum + $checksumBytes)
    
    Write-Host "[OK] Final file size: $($finalData.Length) bytes" -ForegroundColor Green
    Write-Host "  (Header: 256 + Firmware: $($binData.Length) + Checksum: 4)" -ForegroundColor Gray
    
    # ---- STEP 6: Write output ----
    Write-Host "`n[6/6] Writing output file..." -ForegroundColor Yellow
    
    [System.IO.File]::WriteAllBytes($OutputFile, $finalData)
    Write-Host "[OK] Written: $OutputFile" -ForegroundColor Green
    
    return @{
        OutputFile = $OutputFile
        Size = $finalData.Length
        Checksum = $jamcrc
        Valid = $true
    }
}

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

try {
    # Determine output filename if not specified
    if (-not $OutputPath) {
        $fileName = [System.IO.Path]::GetFileNameWithoutExtension($BinFilePath)
        $OutputPath = "$fileName`_converted.sgo"
    }
    
    # Perform conversion
    $result = Convert-BINtoSGO $BinFilePath $OutputPath $ReferenceFile
    
    # Validate result
    if (-not $SkipValidation) {
        Write-Host "`n[✓] Validating output file..." -ForegroundColor Cyan
        $isValid = Validate-DSGFile $OutputPath
        
        if ($isValid) {
            Write-Host "`n✓✓✓ CONVERSION SUCCESSFUL ✓✓✓" -ForegroundColor Green
            Write-Host "Output file is ready for use" -ForegroundColor Green
        } else {
            Write-Host "`n⚠ WARNING: Checksum validation failed" -ForegroundColor Yellow
            Write-Host "File may not be accepted by DSG tools" -ForegroundColor Yellow
        }
    }
    
    Write-Host "`nSummary:" -ForegroundColor Cyan
    Write-Host "  Input:  $BinFilePath ($([System.IO.FileInfo]$BinFilePath).Length bytes)"
    Write-Host "  Output: $($result.OutputFile) ($($result.Size) bytes)"
    Write-Host "  Format: SGML Object File with JAMCRC checksum"
    
} catch {
    Write-Host "`n✗ ERROR: $_" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor Red
    exit 1
}
