# DSG Firmware Checksum Calculator
# Based on research from bri3d/VW_Flash project
# Implements JAMCRC (CRC32 NOT) checksum algorithm

param(
    [Parameter(Mandatory=$false)]
    [string]$FilePath,
    [Parameter(Mandatory=$false)]
    [ValidateSet("Validate", "Fix", "Calculate")]
    [string]$Action = "Validate"
)

# Check if we have required .NET type for CRC32
$hasCrc32 = $false
try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $type = [System.IO.Compression.Crc32]
    $hasCrc32 = $true
} catch {
    Write-Host "Note: System.IO.Compression.Crc32 not available, using alternative method"
}

# Fallback CRC32 implementation if built-in not available
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
    
    <#
    JAMCRC is the bitwise NOT of CRC32
    Formula: JAMCRC = 0xFFFFFFFF - CRC32(data)
    
    This is equivalent to:
    - Taking normal CRC32
    - Inverting all 32 bits
    
    Used in DSG transmission firmware for checksum validation
    #>
    
    $crc32 = Calculate-CRC32 $data
    $jamcrc = 0xFFFFFFFF - $crc32
    
    # Ensure we have proper 32-bit value (no overflow)
    return [uint32]($jamcrc -band 0xFFFFFFFF)
}

function Validate-DSGFile {
    param(
        [string]$FilePath,
        [switch]$Verbose
    )
    
    if (-not (Test-Path $FilePath)) {
        Write-Host "ERROR: File not found: $FilePath" -ForegroundColor Red
        return $null
    }
    
    $data = [System.IO.File]::ReadAllBytes($FilePath)
    
    if ($data.Length -lt 4) {
        Write-Host "ERROR: File too small (less than 4 bytes)" -ForegroundColor Red
        return $null
    }
    
    # Extract stored checksum (last 4 bytes, little-endian)
    $storedChecksumBytes = $data[($data.Length-4)..($data.Length-1)]
    $storedChecksum = [BitConverter]::ToUInt32($storedChecksumBytes, 0)
    
    # Calculate expected checksum (all bytes except last 4)
    $dataForChecksum = $data[0..($data.Length-5)]
    $calculatedChecksum = Calculate-JAMCRC $dataForChecksum
    
    $isValid = $storedChecksum -eq $calculatedChecksum
    
    $result = @{
        FilePath = $FilePath
        FileSize = $data.Length
        Valid = $isValid
        StoredChecksum = "0x$('{0:X8}' -f $storedChecksum)"
        CalculatedChecksum = "0x$('{0:X8}' -f $calculatedChecksum)"
        ChecksumMatch = $isValid
    }
    
    if ($Verbose) {
        Write-Host "`n=== DSG File Checksum Validation ===" -ForegroundColor Cyan
        Write-Host "File:                $($result.FilePath)"
        Write-Host "Size:                $($result.FileSize) bytes"
        Write-Host "Stored Checksum:     $($result.StoredChecksum)"
        Write-Host "Calculated Checksum: $($result.CalculatedChecksum)"
        Write-Host "Status:              $(if ($result.Valid) { 'VALID ✓' } else { 'INVALID ✗' })" `
            -ForegroundColor (if ($result.Valid) { "Green" } else { "Red" })
        
        if (-not $result.Valid) {
            Write-Host "`nWarning: File checksum does not match!" -ForegroundColor Yellow
            Write-Host "Possible causes:" -ForegroundColor Yellow
            Write-Host "  1. File has been modified" -ForegroundColor Yellow
            Write-Host "  2. File was not generated with correct JAMCRC" -ForegroundColor Yellow
            Write-Host "  3. File is corrupted" -ForegroundColor Yellow
        }
    }
    
    return $result
}

function Fix-DSGChecksum {
    param(
        [string]$FilePath,
        [switch]$Backup
    )
    
    if (-not (Test-Path $FilePath)) {
        Write-Host "ERROR: File not found: $FilePath" -ForegroundColor Red
        return $null
    }
    
    # Create backup if requested
    if ($Backup) {
        $backupPath = "$FilePath.backup"
        Copy-Item $FilePath $backupPath
        Write-Host "Backup created: $backupPath" -ForegroundColor Green
    }
    
    $data = [System.IO.File]::ReadAllBytes($FilePath)
    
    if ($data.Length -lt 4) {
        Write-Host "ERROR: File too small (less than 4 bytes)" -ForegroundColor Red
        return $null
    }
    
    # Get all data except last 4 bytes and calculate checksum
    $fileData = $data[0..($data.Length-5)]
    $jamcrc = Calculate-JAMCRC $fileData
    $checksumBytes = [BitConverter]::GetBytes($jamcrc)
    
    # Create final data with new checksum
    $finalData = [byte[]]($fileData + $checksumBytes)
    
    # Write back to file
    [System.IO.File]::WriteAllBytes($FilePath, $finalData)
    
    Write-Host "✓ Checksum fixed: 0x$('{0:X8}' -f $jamcrc)" -ForegroundColor Green
    
    # Verify
    $validation = Validate-DSGFile $FilePath
    if ($validation.Valid) {
        Write-Host "✓ Validation successful" -ForegroundColor Green
    } else {
        Write-Host "✗ Validation failed - file may be corrupted" -ForegroundColor Red
    }
    
    return $jamcrc
}

function Show-Help {
    Write-Host @"
DSG Firmware Checksum Calculator v1.0
Based on: bri3d/VW_Flash JAMCRC implementation

USAGE:
    .\DSG_Checksum.ps1 -FilePath <path> -Action <action>

ACTIONS:
    Validate  - Check if file has valid checksum (default)
    Fix       - Recalculate and fix checksum
    Calculate - Just calculate without modifying

EXAMPLES:
    # Validate a file
    .\DSG_Checksum.ps1 -FilePath "firmware.sgo"
    
    # Fix checksum with backup
    .\DSG_Checksum.ps1 -FilePath "firmware.sgo" -Action Fix -Backup
    
    # Just calculate
    .\DSG_Checksum.ps1 -FilePath "firmware.bin" -Action Calculate

CHECKSUM DETAILS:
    Type:           JAMCRC (CRC32 NOT)
    Formula:        JAMCRC = 0xFFFFFFFF - CRC32(data)
    Location:       Last 4 bytes of file (little-endian)
    Data included:  All bytes except last 4
    Used by:        DSG transmission firmware validation

ABOUT:
    DSG transmissions use JAMCRC for firmware integrity checking.
    This is NOT standard CRC32 - it's the bitwise NOT of CRC32.
    
    Reference: https://github.com/bri3d/VW_Flash/blob/master/lib/dsg_checksum.py
"@
}

# Main execution
if (-not $FilePath -or $FilePath -eq "?" -or $FilePath -eq "help") {
    Show-Help
    exit 0
}

switch ($Action) {
    "Validate" {
        $result = Validate-DSGFile $FilePath -Verbose
        exit 0
    }
    "Fix" {
        Write-Host "Fixing checksum for: $FilePath" -ForegroundColor Cyan
        Fix-DSGChecksum $FilePath -Backup
        exit 0
    }
    "Calculate" {
        $data = [System.IO.File]::ReadAllBytes($FilePath)
        $fileData = $data[0..($data.Length-5)]
        $jamcrc = Calculate-JAMCRC $fileData
        Write-Host "Calculated JAMCRC: 0x$('{0:X8}' -f $jamcrc)" -ForegroundColor Cyan
        exit 0
    }
    default {
        Write-Host "Unknown action: $Action" -ForegroundColor Red
        Show-Help
        exit 1
    }
}
