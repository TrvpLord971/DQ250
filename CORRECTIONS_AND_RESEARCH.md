# CORRECTION ANALYSIS - DSG Firmware File Format Research

## 🔍 Research Summary

After researching GitHub repositories and automotive firmware documentation, particularly the **bri3d/VW_Flash** project which has extensive DSG documentation and tools, several corrections and clarifications are needed regarding the initial analysis.

---

## ✅ Confirmed Findings

### What Was Correct:
1. ✅ **File format identification**: .BIN, .ORI, .SGO are distinct firmware formats
2. ✅ **SGML container structure**: .SGO uses SGML Object File wrapper
3. ✅ **Data preservation**: Firmware data is preserved byte-for-byte
4. ✅ **Footer metadata**: All formats contain version strings and metadata
5. ✅ **DSG transmission type**: RM8H variant identification is correct

---

## ❌ Corrections & Important Discoveries

### 1. CHECKSUM ALGORITHM - CRITICAL CORRECTION

**Previous Analysis (INCORRECT):**
- Stated checksum was 14 bytes of unknown data
- Did not identify the checksum algorithm

**CORRECT INFORMATION (from bri3d/VW_Flash):**
```
DSG uses JAMCRC - the bitwise NOT of CRC32
Location: Last 4 bytes of file (little-endian uint32)
Calculation: JAMCRC = 0xFFFFFFFF - CRC32(data_without_last_4_bytes)

Algorithm implementation:
import zlib
import struct

def calculate_jamcrc(data):
    checksum_data = data[:-4]  # All bytes except last 4
    checksum = int("0b" + "1" * 32, 2) - zlib.crc32(checksum_data)
    return checksum & 0xFFFFFFFF  # Ensure 32-bit
```

**Impact on our conversion:**
- The 14-byte "checksum data" I identified is NOT the checksum
- Real checksum is only 4 bytes (last 4 bytes of file)
- Checksums need to be recalculated using JAMCRC if modified
- My converter currently copied reference checksums (incorrect approach)

---

### 2. DSG ENCRYPTION - NOT STANDARD

**Previous Analysis (INCOMPLETE):**
- Did not mention encryption

**CORRECT INFORMATION:**
- DSG uses a **256-byte substitution cipher** with rolling offset
- However: **DSG accepts uncompressed, unencrypted payloads**
- Files can be encrypted/compressed OR plain binary
- Our .BIN file appears to be **unencrypted** (based on readable instruction patterns)

**Encryption details** (from bri3d/VW_Flash):
```python
# Rolling-offset substitution cipher
# Components:
# 1. Rolling key offset (maintains state)
# 2. Previous data byte contribution
# 3. Rolling stream of key data (incremented by 0x167)
# 4. 256-byte substitution table lookup

# Not used in our files (they appear unencrypted)
```

---

### 3. DSG COMPRESSION - LZSS Not Applied

**Previous Analysis (INCOMPLETE):**
- Did not mention compression

**CORRECT INFORMATION:**
- DSG supports **LZSS compression** (custom variant)
- Our .BIN files appear **uncompressed**
- Firmware data is readable as raw machine code

---

### 4. FILE FORMAT PURPOSE - CLARIFICATION

**Previous Analysis (PARTIAL):**
- Stated .SGO is for "diagnostic tools" (correct)
- Did not explain the full purpose

**CORRECT INFORMATION:**
From bri3d/VW_Flash documentation:
- **.ORI**: Reference/original format (rarely used in field)
- **.BIN**: Raw binary programming format (direct ECU writes)
- **.SGO**: SGML container for ODX/flash packages (production distribution)
- **ODX**: Complete flash container (higher-level format containing .SGO)

---

### 5. HEADER STRUCTURE - Partially Misidentified

**Previous Analysis (INCOMPLETE):**
- Identified "address markers" as 0x48 0x00 pattern
- Did not explain their purpose

**CORRECT INFORMATION (partial):**
The 0x48 0x00 pattern in header likely represents:
- Section references/size indicators
- NOT direct memory addresses (my assumption was simplified)
- Actual interpretation requires deeper reverse-engineering

**What we know for sure:**
- Header contains calibration section references
- Multiple blocks can be encrypted/compressed independently
- Address table helps bootloader locate sections during flash

---

### 6. METADATA SECTION - Correction

**Previous Analysis (INACCURATE):**
- Stated encoded section was "compressed transmission info"
- Provided no basis for the claim

**CORRECT INFORMATION:**
The 48-byte encoded section at offset 0x30-0x5F:
- Contains encoded calibration/variant metadata
- Encoding method: Unknown (not documented in public sources)
- Appears to identify: Transmission type, software version, calibration level
- Our analysis correctly identified the VERSION but not the encoding

---

## 🔧 Improvements Needed for Converter

### 1. Checksum Calculation - MUST FIX

**Current Code (WRONG):**
```powershell
# Currently just copies reference checksums
$checksumData = @(0x60, 0x8B, 0x14, 0xAE, 0xF8, 0x5F, 0x39, 0x3F, ...)
```

**Should Be (CORRECT):**
```powershell
# Implement JAMCRC calculation
function Calculate-JAMCRC {
    param([byte[]]$data)
    
    $crc32 = [System.IO.Compression.Crc32]::Checksum($data)
    $jamcrc = 0xFFFFFFFF - $crc32
    return [uint32]$jamcrc
}

# Then append to file:
$fileData = $sgoHeader + $firmwareData
$jamcrc = Calculate-JAMCRC($fileData[0..($fileData.Length-5)])
$finalData = $fileData[0..($fileData.Length-5)] + [BitConverter]::GetBytes($jamcrc)
```

### 2. Validation - MUST ADD

**Currently Missing:**
- No checksum validation in converter
- No integrity checking output

**Should Add:**
```powershell
# Calculate expected vs actual checksum
function Validate-DSGChecksum {
    param([string]$FilePath)
    
    $data = [System.IO.File]::ReadAllBytes($FilePath)
    $storedChecksum = [BitConverter]::ToUInt32($data[-4..-1], 0)
    $calculatedChecksum = Calculate-JAMCRC($data[0..($data.Length-5)])
    
    return $storedChecksum -eq $calculatedChecksum
}
```

---

## 📊 Updated File Structure Analysis

### Corrected .BIN Format Layout
```
Offset 0x0000-0x01FF (512 bytes):  Address Reference Table
  - Section references for firmware blocks
  - Layout references for bootloader
  - NOT direct memory addresses

Offset 0x0200-0x6FFEF (458,735 bytes):  Unencrypted Firmware Data
  - Machine code (readable patterns: 0x20 0x00 0x81 = valid instruction)
  - Initialization data
  - Clear text calibration references

Offset 0x6FFBB-0x6FFFF (69 bytes):  Metadata Footer
  - Version string: "v0698H0102ea__getriebe_DSG_RM8H" (34 bytes)
  - Padding: 0x00 0x00 (2 bytes)
  - Reserved/unknown: Several bytes
  - JAMCRC Checksum: Last 4 bytes (MUST BE CALCULATED, not copied)
```

### Corrected .SGO Format Layout
```
Offset 0x0000-0x00FF (256 bytes):  SGML Header
  - Magic: "SGML Object File"
  - Version: 0x0200
  - Metadata references
  - Encoded variant info (encoding algorithm unknown)

Offset 0x0100+:  Wrapped Firmware Data
  - Same .BIN content (unencrypted/uncompressed)
  - Byte-for-byte identical to source

Offset EOF-64..EOF (64 bytes):  Footer
  - Same structure as .BIN
  - JAMCRC Checksum: Last 4 bytes
```

---

## 🎯 Impact Assessment

### High Priority Issues:
1. ❌ **Checksum calculation is WRONG** - Currently copies reference values
   - Impact: Files won't validate with real DSG tools
   - Fix difficulty: MEDIUM (implement JAMCRC)
   - Status: NEEDS IMMEDIATE CORRECTION

2. ❌ **Checksum validation is MISSING** - No output validation
   - Impact: User doesn't know if conversion is valid
   - Fix difficulty: LOW
   - Status: NEEDS ADDITION

### Medium Priority Issues:
3. ⚠️ **Metadata encoding unknown** - 48-byte section at 0x30-0x5F
   - Impact: If file needs to be modified, can't update metadata
   - Fix difficulty: HIGH (requires more reverse-engineering)
   - Status: Document as limitation

4. ⚠️ **Header address table purpose unclear** - 0x48 0x00 pattern
   - Impact: Educational (doesn't affect current conversion)
   - Fix difficulty: HIGH
   - Status: Note in documentation

### Low Priority Issues:
5. ℹ️ **Optional: Encryption/compression support**
   - Impact: Current files don't use it
   - Fix difficulty: HIGH
   - Status: Future enhancement

---

## ✅ Recommended Corrections

### Priority 1 - CRITICAL: Implement JAMCRC
Create new file: `DSG_Checksum.ps1`

```powershell
# Load required assembly for CRC32
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Calculate-CRC32 {
    param([byte[]]$data)
    return [System.IO.Compression.Crc32]::Checksum($data, 0, $data.Length)
}

function Calculate-JAMCRC {
    param([byte[]]$data)
    $crc32 = Calculate-CRC32 $data
    $jamcrc = 0xFFFFFFFF - $crc32
    return [uint32]($jamcrc -band 0xFFFFFFFF)
}

function Validate-DSGFile {
    param([string]$FilePath)
    
    $data = [System.IO.File]::ReadAllBytes($FilePath)
    if ($data.Length -lt 4) { return $false }
    
    $storedChecksum = [BitConverter]::ToUInt32($data[-4..-1], 0)
    $calculatedChecksum = Calculate-JAMCRC $data[0..($data.Length-5)]
    
    return @{
        Valid = $storedChecksum -eq $calculatedChecksum
        StoredChecksum = "0x$('{0:X8}' -f $storedChecksum)"
        CalculatedChecksum = "0x$('{0:X8}' -f $calculatedChecksum)"
    }
}

function Fix-DSGChecksum {
    param([string]$FilePath)
    
    $data = [System.IO.File]::ReadAllBytes($FilePath)
    $fileData = $data[0..($data.Length-5)]
    $jamcrc = Calculate-JAMCRC $fileData
    
    $finalData = [byte[]]($fileData + [BitConverter]::GetBytes($jamcrc))
    [System.IO.File]::WriteAllBytes($FilePath, $finalData)
    
    return "Checksum fixed: 0x$('{0:X8}' -f $jamcrc)"
}
```

### Priority 2 - Integrate Checksum Validation
Update: `BIN_to_SGO_Converter.ps1`

```powershell
# Add after final write:
$validation = Validate-DSGFile $OutputSgoFile
Write-Host "`nChecksum Validation:"
Write-Host "  Stored:      $($validation.StoredChecksum)"
Write-Host "  Calculated:  $($validation.CalculatedChecksum)"
Write-Host "  Status:      $(if ($validation.Valid) { 'VALID ✓' } else { 'INVALID ✗' })"

if (-not $validation.Valid) {
    Write-Host "  WARNING: Checksums don't match!"
    Write-Host "  Run: Fix-DSGChecksum '$OutputSgoFile'"
}
```

### Priority 3 - Document Limitations
Update: `CONVERSION_ANALYSIS.md`

```markdown
## ⚠️ Known Limitations

1. **Checksum Calculation**: Uses JAMCRC (CRC32 NOT)
   - Implemented from bri3d/VW_Flash research
   - Must match for DSG tools to accept file

2. **Metadata Encoding**: 48-byte section uses unknown encoding
   - Not documented in public sources
   - Current converter copies reference values
   - Files should still work if firmware data unchanged

3. **Encryption/Compression**: Not currently supported
   - Source .BIN files are unencrypted/uncompressed
   - If needed in future, requires implementing:
     - DSG 256-byte substitution cipher
     - LZSS compression/decompression
```

---

## 📚 Research Sources

Found and reviewed:

1. **bri3d/VW_Flash** (GitHub)
   - `/lib/dsg_checksum.py` - JAMCRC algorithm
   - `/lib/crypto/dsg.py` - Encryption details
   - `/docs/dsg.md` - DSG format documentation
   - Confirms: JAMCRC checksum, rolling cipher encryption, LZSS compression

2. **bri3d/VW_Flash** continued
   - `/docs/docs.md` - Simos ECU architecture (referenced for understanding firmware structure)
   - Extensive documentation on Tricore processor and boot chain

3. **Wikipedia - SGML**
   - Confirmed SGML is markup language standard (not specifically for firmware)
   - Our use case (binary wrapper with SGML magic) is non-standard adaptation

---

## 🎓 Key Learnings

1. **DSG is relatively unprotected** - Uses simple encryption, simple checksums
2. **JAMCRC != CRC32** - Many people confuse these; JAMCRC is bitwise NOT of CRC32
3. **File can be unencrypted** - DSG controller accepts plain binary
4. **Metadata encoding is proprietary** - No public documentation available
5. **Research matters** - Initial reverse-engineering missed critical checksum details

---

## 📋 Summary of Changes Needed

| Item | Severity | Status | Fix |
|------|----------|--------|-----|
| Checksum calculation | 🔴 CRITICAL | ❌ WRONG | Implement JAMCRC |
| Checksum validation | 🔴 CRITICAL | ❌ MISSING | Add validation output |
| Metadata encoding | 🟡 MEDIUM | ⚠️ PARTIAL | Document limitation |
| File format docs | 🟡 MEDIUM | ✅ GOOD | Minor updates needed |
| Encryption support | 🟢 LOW | ⚠️ N/A | Document as future feature |

---

## ✨ Conclusion

The original analysis was **60% correct** in structure but **critically wrong** about checksums. The conversion tool will create SGML-valid files but **will NOT pass DSG validation** because checksums are incorrect. This needs immediate fixing.

The good news: JAMCRC is simple to implement and the fix is straightforward.

---

**Updated**: 2026-08-26 (Post-Research)  
**Status**: Analysis corrected based on GitHub research  
**Next Step**: Implement JAMCRC checksum calculation
