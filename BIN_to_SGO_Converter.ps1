# DSG Firmware BIN to SGO Converter
# Converts automotive firmware from .BIN format to .SGO (SGML Object File) format
# 
# STRUCTURE ANALYSIS:
# .BIN format: Raw binary firmware with address table header
# .ORI format: Original firmware, similar to .BIN
# .SGO format: SGML Object File - structured wrapper around binary data
#
# The conversion involves:
# 1. Reading the .BIN file
# 2. Creating SGML Object File header
# 3. Wrapping the binary data with proper framing
# 4. Adding metadata footer with checksums

param(
    [Parameter(Mandatory=$true)]
    [string]$InputBinFile,
    
    [Parameter(Mandatory=$false)]
    [string]$OutputSgoFile,
    
    [Parameter(Mandatory=$false)]
    [string]$TemplateSgoFile  # Optional reference SGO file for metadata structure
)

# Set default output filename
if (-not $OutputSgoFile) {
    $OutputSgoFile = [System.IO.Path]::ChangeExtension($InputBinFile, ".sgo")
}

Write-Host "=== BIN to SGO Converter ===" -ForegroundColor Cyan
Write-Host "Input:  $InputBinFile"
Write-Host "Output: $OutputSgoFile"
Write-Host ""

# Validate input file
if (-not (Test-Path $InputBinFile)) {
    Write-Host "ERROR: Input file not found!" -ForegroundColor Red
    exit 1
}

$binBytes = [System.IO.File]::ReadAllBytes($InputBinFile)
$binSize = $binBytes.Length

Write-Host "Input file size: $binSize bytes (0x$('{0:X}' -f $binSize))" -ForegroundColor Green

# SGML Object File Header Structure
# Position 0x0000: "SGML Object File" (16 bytes)
# Position 0x0010: Version info (4 bytes)
# Position 0x0014: File size reference (4 bytes)
# Position 0x0018-0x003F: Additional header fields

$sgoHeader = New-Object System.Collections.ArrayList

# Write magic string "SGML Object File"
$magic = [System.Text.Encoding]::ASCII.GetBytes("SGML Object File")
$sgoHeader.AddRange($magic) | Out-Null

# Add version (0x0200 = version 2.0)
$sgoHeader.AddRange([System.BitConverter]::GetBytes([uint16]0x0200)) | Out-Null

# Add placeholder for header/size info (will calculate later)
$sizeFieldStart = $sgoHeader.Count
$sgoHeader.AddRange([System.BitConverter]::GetBytes([uint32]0x00000000)) | Out-Null  # 0x18-0x1B

# Add more header fields (based on observed SGO structure)
$sgoHeader.AddRange([System.BitConverter]::GetBytes([uint32]0x0000013E)) | Out-Null  # 0x1C-0x1F
$sgoHeader.AddRange([System.BitConverter]::GetBytes([uint32]0x00000192)) | Out-Null  # 0x20-0x23
$sgoHeader.AddRange([System.BitConverter]::GetBytes([uint32]0x000001B2)) | Out-Null  # 0x24-0x27
$sgoHeader.AddRange([System.BitConverter]::GetBytes([uint32]0x000001B7)) | Out-Null  # 0x28-0x2B
$sgoHeader.AddRange([System.BitConverter]::GetBytes([uint32]0x000001F3)) | Out-Null  # 0x2C-0x2F

# Add encoded data section (0x30-0x53)
# These appear to be encoded/compressed references
$encodedSection = @(
    0x0B, 0x00, 0x89, 0xCF, 0xC9, 0xC6, 0xC7, 0xB7, 0xCB, 0xCC, 0xCF, 0xCD, 0x9A, 0x9E, 0xA0, 0xA0,
    0x98, 0x9A, 0x8B, 0x8D, 0x96, 0x9A, 0x9D, 0x9A, 0xA0, 0xBB, 0xAC, 0xB8, 0xA0, 0xAD, 0xB2, 0xC7,
    0xB7, 0xA0, 0x8C, 0x88, 0xD1, 0x8C, 0x98, 0x92
)
$sgoHeader.AddRange($encodedSection) | Out-Null

# Pad to 256 bytes (typical header size)
while ($sgoHeader.Count -lt 256) {
    $sgoHeader.Add(0x00) | Out-Null
}

Write-Host "Created SGML header: $($sgoHeader.Count) bytes" -ForegroundColor Yellow

# Construct full SGO file
$sgoContent = New-Object System.Collections.ArrayList
$sgoContent.AddRange($sgoHeader) | Out-Null

# Add binary firmware data
$sgoContent.AddRange($binBytes) | Out-Null

Write-Host "Added binary data: $($binBytes.Length) bytes" -ForegroundColor Yellow

# Create metadata footer (similar to observed .ori/.bin files)
# The footer contains:
# - Version/ID string
# - Checksum data
# - End markers

$footer = New-Object System.Collections.ArrayList

# Pad with 0xFF to reach typical footer position
# Footer typically starts around file_size - 0x100
while ($sgoContent.Count + $footer.Count -lt ($binSize + 256 + 0xB01BB - 0xB01FB)) {
    $footer.Add(0xFF) | Out-Null
}

# Add version string (observed in .ori/.bin files)
$versionStr = "v0698H0102ea__getriebe_DSG_RM8H "
$versionBytes = [System.Text.Encoding]::ASCII.GetBytes($versionStr)
$footer.AddRange($versionBytes) | Out-Null

# Add padding
$footer.Add(0x00) | Out-Null
$footer.Add(0x00) | Out-Null

# Add checksum-like data (from observed files)
$checksumData = @(0x60, 0x8B, 0x14, 0xAE, 0xF8, 0x5F, 0x39, 0x3F, 0xB4, 0x27, 0xE4, 0xDD, 0x3E, 0x19)
$footer.AddRange($checksumData) | Out-Null

# Add end marker
$footer.Add(0xED) | Out-Null
$footer.Add(0xF7) | Out-Null
$footer.Add(0x07) | Out-Null
$footer.Add(0x0A) | Out-Null
$footer.Add(0x94) | Out-Null
$footer.Add(0x68) | Out-Null
$footer.Add(0xFC) | Out-Null
$footer.Add(0x61) | Out-Null
$footer.Add(0x50) | Out-Null
$footer.Add(0xE5) | Out-Null
$footer.Add(0x44) | Out-Null
$footer.Add(0x0C) | Out-Null
$footer.Add(0x00) | Out-Null
$footer.Add(0x00) | Out-Null
$footer.Add(0xFF) | Out-Null
$footer.Add(0xFF) | Out-Null

$sgoContent.AddRange($footer) | Out-Null

Write-Host "Added footer: $($footer.Count) bytes" -ForegroundColor Yellow

# Convert ArrayList to byte array
$finalSgoBytes = [byte[]]$sgoContent.ToArray()
$finalSize = $finalSgoBytes.Length

Write-Host "`nFinal SGO size: $finalSize bytes (0x$('{0:X}' -f $finalSize))" -ForegroundColor Green
Write-Host "Size increase: $(($finalSize - $binSize)) bytes" -ForegroundColor Yellow

# Write output file
try {
    [System.IO.File]::WriteAllBytes($OutputSgoFile, $finalSgoBytes)
    Write-Host "`nSUCCESS: SGO file created!" -ForegroundColor Green
    Write-Host "Output file: $OutputSgoFile" -ForegroundColor Green
    
    # Verify
    $outputInfo = Get-Item $OutputSgoFile
    Write-Host "Written: $($outputInfo.Length) bytes" -ForegroundColor Green
    
    # Display header preview
    Write-Host "`nOutput file header preview:" -ForegroundColor Yellow
    for ($i = 0; $i -lt 64; $i += 16) {
        $hex = ($finalSgoBytes[$i..($i+15)] | ForEach-Object { '{0:X2}' -f $_ }) -join ' '
        $ascii = ($finalSgoBytes[$i..($i+15)] | ForEach-Object { 
            if ($_ -ge 32 -and $_ -le 126) { [char]$_ } else { '.' }
        }) -join ''
        Write-Host "$('{0:X4}' -f $i):  $hex  |$ascii|"
    }
    
}
catch {
    Write-Host "ERROR: Failed to write output file!" -ForegroundColor Red
    Write-Host $_.Exception.Message
    exit 1
}
