#!/usr/bin/env python3
"""
DSG Firmware BIN to SGO Converter with JAMCRC Checksum
Based on research from bri3d/VW_Flash project

JAMCRC Formula: JAMCRC = 0xFFFFFFFF - CRC32(data)
This is the correct checksum algorithm for DSG transmissions.
"""

import sys
import struct
import zlib
import os
from pathlib import Path


class DSGChecksum:
    """JAMCRC checksum calculator for DSG firmware"""
    
    @staticmethod
    def calculate_crc32(data: bytes) -> int:
        """Calculate standard CRC32"""
        return zlib.crc32(data) & 0xFFFFFFFF
    
    @staticmethod
    def calculate_jamcrc(data: bytes) -> int:
        """
        Calculate JAMCRC (bitwise NOT of CRC32)
        This is the checksum algorithm used in DSG transmissions
        """
        crc32_val = DSGChecksum.calculate_crc32(data)
        jamcrc = (0xFFFFFFFF - crc32_val) & 0xFFFFFFFF
        return jamcrc
    
    @staticmethod
    def validate_file(filepath: str) -> dict:
        """Validate a DSG firmware file"""
        with open(filepath, 'rb') as f:
            data = f.read()
        
        if len(data) < 4:
            return {'valid': False, 'error': 'File too small'}
        
        # Extract stored checksum (last 4 bytes, little-endian)
        stored_checksum = struct.unpack('<I', data[-4:])[0]
        
        # Calculate expected checksum (all data except last 4 bytes)
        data_for_checksum = data[:-4]
        calculated_checksum = DSGChecksum.calculate_jamcrc(data_for_checksum)
        
        return {
            'valid': stored_checksum == calculated_checksum,
            'file_size': len(data),
            'stored': f'0x{stored_checksum:08X}',
            'calculated': f'0x{calculated_checksum:08X}',
            'match': stored_checksum == calculated_checksum
        }
    
    @staticmethod
    def fix_file(filepath: str, backup=True) -> bool:
        """Recalculate and fix checksum in a file"""
        # Create backup
        if backup:
            backup_path = f"{filepath}.backup"
            with open(filepath, 'rb') as src:
                with open(backup_path, 'wb') as dst:
                    dst.write(src.read())
            print(f"[OK] Backup created: {backup_path}")
        
        # Read file
        with open(filepath, 'rb') as f:
            data = f.read()
        
        # Calculate new JAMCRC (all data except last 4 bytes)
        data_for_checksum = data[:-4]
        jamcrc = DSGChecksum.calculate_jamcrc(data_for_checksum)
        
        # Write back
        new_data = data_for_checksum + struct.pack('<I', jamcrc)
        with open(filepath, 'wb') as f:
            f.write(new_data)
        
        print(f"[OK] Checksum fixed: 0x{jamcrc:08X}")
        return True


class BINtoSGOConverter:
    """Convert DSG firmware from BIN to SGO format with JAMCRC"""
    
    SGML_MAGIC = b'SGML Object File'
    SGML_VERSION = b'\x00\x02'
    SGML_HEADER_SIZE = 256
    
    def __init__(self, bin_filepath: str, reference_filepath: str = None):
        self.bin_filepath = bin_filepath
        self.reference_filepath = reference_filepath
        
        # Read input file
        if not os.path.exists(bin_filepath):
            raise FileNotFoundError(f"BIN file not found: {bin_filepath}")
        
        with open(bin_filepath, 'rb') as f:
            self.bin_data = f.read()
        
        # Read reference if provided
        self.reference_data = None
        if reference_filepath and os.path.exists(reference_filepath):
            with open(reference_filepath, 'rb') as f:
                self.reference_data = f.read()
    
    def create_sgml_header(self) -> bytes:
        """Create SGML header (256 bytes)"""
        header = bytearray(self.SGML_HEADER_SIZE)
        
        # SGML magic signature
        header[:len(self.SGML_MAGIC)] = self.SGML_MAGIC
        
        # Version
        header[16:18] = self.SGML_VERSION
        
        # Copy metadata from reference if available
        if self.reference_data and len(self.reference_data) >= 256:
            # Copy encoded metadata section (offsets 0x18-0x5F)
            header[0x18:0x18+0x48] = self.reference_data[0x18:0x18+0x48]
            
            # Copy remaining header fields
            header[0x60:] = self.reference_data[0x60:0x60+0xA0]
        
        return bytes(header)
    
    def convert(self, output_filepath: str = None) -> dict:
        """
        Convert BIN file to SGO format with proper JAMCRC checksum
        
        Returns: dict with conversion details
        """
        if not output_filepath:
            # Generate output filename
            base_name = Path(self.bin_filepath).stem
            output_filepath = f"{base_name}_converted.sgo"
        
        print("\n" + "="*50)
        print("BIN to SGO Converter v2.0 (JAMCRC Corrected)")
        print("="*50 + "\n")
        
        # Step 1: Create header
        print("[1/5] Creating SGML header...")
        sgml_header = self.create_sgml_header()
        print(f"[OK] Header created: {len(sgml_header)} bytes")
        
        # Step 2: Combine header + firmware
        print("\n[2/5] Combining header and firmware...")
        combined_data = sgml_header + self.bin_data
        print(f"[OK] Combined size: {len(combined_data)} bytes")
        print(f"     (Header: {len(sgml_header)} + Firmware: {len(self.bin_data)})")
        
        # Step 3: Calculate JAMCRC
        print("\n[3/5] Calculating JAMCRC checksum...")
        data_for_checksum = combined_data[:-4] if len(combined_data) >= 4 else combined_data
        jamcrc = DSGChecksum.calculate_jamcrc(data_for_checksum)
        print(f"[OK] JAMCRC: 0x{jamcrc:08X}")
        print(f"     Formula: JAMCRC = 0xFFFFFFFF - CRC32(data)")
        
        # Step 4: Build final file
        print("\n[4/5] Building final SGO file...")
        checksum_bytes = struct.pack('<I', jamcrc)
        final_data = data_for_checksum + checksum_bytes
        print(f"[OK] Final size: {len(final_data)} bytes")
        
        # Step 5: Write output
        print("\n[5/5] Writing output file...")
        with open(output_filepath, 'wb') as f:
            f.write(final_data)
        print(f"[OK] Written: {output_filepath}")
        
        # Step 6: Validate
        print("\n[Validation] Checking output file...")
        validation = DSGChecksum.validate_file(output_filepath)
        
        if validation['valid']:
            print("[SUCCESS] Output file is VALID!")
            print(f"  Stored checksum:      {validation['stored']}")
            print(f"  Calculated checksum:  {validation['calculated']}")
        else:
            print("[WARNING] Output file validation FAILED")
            print(f"  Stored checksum:      {validation['stored']}")
            print(f"  Calculated checksum:  {validation['calculated']}")
        
        print("\n" + "="*50)
        print("Summary:")
        print(f"  Input:   {self.bin_filepath} ({len(self.bin_data)} bytes)")
        print(f"  Output:  {output_filepath} ({len(final_data)} bytes)")
        print(f"  Format:  SGML Object File with JAMCRC checksum")
        print(f"  Status:  {'VALID' if validation['valid'] else 'INVALID'}")
        print("="*50 + "\n")
        
        return {
            'output_file': output_filepath,
            'size': len(final_data),
            'jamcrc': jamcrc,
            'valid': validation['valid'],
            'validation': validation
        }


def main():
    """Command-line interface"""
    if len(sys.argv) < 2:
        print("""
DSG Firmware BIN to SGO Converter v2.0

USAGE:
    python bin_to_sgo.py <input.bin> [output.sgo] [reference.sgo]

ARGUMENTS:
    input.bin       - Source BIN firmware file (required)
    output.sgo      - Output SGO file (optional, auto-generated if not provided)
    reference.sgo   - Reference SGO file for metadata (optional)

EXAMPLES:
    # Convert with auto-generated output
    python bin_to_sgo.py firmware.bin
    
    # Convert with reference for metadata
    python bin_to_sgo.py firmware.bin output.sgo reference.sgo
    
    # Validate existing file
    python bin_to_sgo.py --validate firmware.sgo

CHECKSUM:
    Uses JAMCRC (bitwise NOT of CRC32) as per DSG specification
    Formula: JAMCRC = 0xFFFFFFFF - CRC32(data)
    Location: Last 4 bytes of file (little-endian)

REFERENCE:
    Based on bri3d/VW_Flash project
    https://github.com/bri3d/VW_Flash/blob/master/lib/dsg_checksum.py
""")
        sys.exit(1)
    
    # Parse arguments
    if sys.argv[1] == '--validate':
        if len(sys.argv) < 3:
            print("Usage: python bin_to_sgo.py --validate <file>")
            sys.exit(1)
        
        result = DSGChecksum.validate_file(sys.argv[2])
        print(f"\nFile: {sys.argv[2]}")
        print(f"Size: {result['file_size']} bytes")
        print(f"Stored:      {result['stored']}")
        print(f"Calculated:  {result['calculated']}")
        print(f"Status:      {'VALID' if result['valid'] else 'INVALID'}")
        sys.exit(0 if result['valid'] else 1)
    
    bin_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    reference_file = sys.argv[3] if len(sys.argv) > 3 else None
    
    try:
        converter = BINtoSGOConverter(bin_file, reference_file)
        result = converter.convert(output_file)
        sys.exit(0 if result['valid'] else 1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
