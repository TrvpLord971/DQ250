#!/usr/bin/env python3
"""
Audi Flashdaten Firmware Analysis Tool
Multi-format firmware analyzer for FRF, SGO, BIN, and ODX files
Extracts software IDs, calibration data, and firmware structures
"""

import os
import sys
import struct
import hashlib
import json
import re
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Tuple, Optional


class FirmwareAnalyzer:
    """Analyze firmware files and extract metadata"""
    
    # Magic byte signatures for file types
    SIGNATURES = {
        b'SGML Object File': 'SGO',
        b'FRF': 'FRF',
        b'<?xml': 'XML/ODX',
        b'\x78\x9c': 'ZLIB_COMPRESSED',
        b'\x1f\x8b': 'GZIP_COMPRESSED',
        b'PK\x03\x04': 'ZIP',
    }
    
    # Common firmware string patterns
    STRING_PATTERNS = [
        rb'v\d{4}[A-Z]\d{2}[a-f0-9]{2}',  # Version pattern
        rb'DSG|DQ\d{3}|RM\d[A-Z]',  # Gearbox models
        rb'0x[0-9A-Fa-f]{8}',  # Memory addresses
        rb'_\w+_\d{2,5}[_\.sgo|\.bin]',  # File patterns
    ]
    
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.filename = Path(filepath).name
        self.file_ext = Path(filepath).suffix.lower()
        self.data = None
        self.metadata = {}
        
    def load_file(self) -> bool:
        """Load file into memory"""
        try:
            with open(self.filepath, 'rb') as f:
                self.data = f.read()
            return True
        except Exception as e:
            print(f"Error loading {self.filepath}: {e}")
            return False
    
    def get_file_hash(self, algorithm='sha256') -> str:
        """Calculate file hash"""
        if algorithm == 'md5':
            return hashlib.md5(self.data).hexdigest()
        elif algorithm == 'sha1':
            return hashlib.sha1(self.data).hexdigest()
        else:
            return hashlib.sha256(self.data).hexdigest()
    
    def detect_file_type(self) -> str:
        """Detect actual file type from magic bytes"""
        for magic, filetype in self.SIGNATURES.items():
            if self.data.startswith(magic):
                return filetype
        return "UNKNOWN"
    
    def extract_strings(self, min_length: int = 4) -> List[str]:
        """Extract ASCII strings from binary"""
        strings = []
        current = []
        
        for byte in self.data:
            if 32 <= byte <= 126:  # Printable ASCII
                current.append(chr(byte))
            else:
                if len(current) >= min_length:
                    strings.append(''.join(current))
                current = []
        
        if len(current) >= min_length:
            strings.append(''.join(current))
        
        return strings
    
    def extract_version_strings(self) -> List[str]:
        """Extract version information strings"""
        versions = []
        
        # Look for common version patterns
        patterns = [
            rb'v\d{4}[A-Z]\d{2}[a-f0-9]{2}',  # v0698H0102ea
            rb'\d+\.\d+\.\d+',  # x.x.x version
            rb'[vV](?:ersion)?[\s_]*(\d+\.?\d*)',
            rb'Build[\s_]*(\d+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, self.data)
            for match in matches:
                if isinstance(match, bytes):
                    versions.append(match.decode('utf-8', errors='ignore'))
                else:
                    versions.append(str(match))
        
        return versions
    
    def analyze_header(self) -> Dict:
        """Analyze file header"""
        header_info = {
            'file_size': len(self.data),
            'detected_type': self.detect_file_type(),
            'file_extension': self.file_ext,
            'hash_md5': self.get_file_hash('md5'),
            'magic_bytes': self.data[:32].hex(),
        }
        
        # Extract header based on file type
        if self.file_ext == '.sgo':
            header_info.update(self.analyze_sgo_header())
        elif self.file_ext == '.frf':
            header_info.update(self.analyze_frf_header())
        elif self.file_ext == '.bin':
            header_info.update(self.analyze_bin_header())
        
        return header_info
    
    def analyze_sgo_header(self) -> Dict:
        """Analyze SGO (SGML Object File) header"""
        if not self.data.startswith(b'SGML Object File'):
            return {}
        
        sgo_info = {
            'format': 'SGML Object File',
            'magic': 'SGML Object File',
        }
        
        # Extract version (bytes 16-17)
        if len(self.data) >= 18:
            version = struct.unpack('<H', self.data[16:18])[0]
            sgo_info['version_field'] = f'0x{version:04X}'
        
        # Look for JAMCRC checksum (last 4 bytes)
        if len(self.data) >= 4:
            jamcrc = struct.unpack('<I', self.data[-4:])[0]
            sgo_info['jamcrc_checksum'] = f'0x{jamcrc:08X}'
        
        return sgo_info
    
    def analyze_frf_header(self) -> Dict:
        """Analyze FRF header"""
        frf_info = {'format': 'FRF'}
        
        # FRF is typically a flash container
        # Look for embedded structures
        if b'FRF' in self.data[:100]:
            frf_info['contains_frf_header'] = True
        
        return frf_info
    
    def analyze_bin_header(self) -> Dict:
        """Analyze BIN header"""
        bin_info = {
            'format': 'Binary',
            'first_bytes': self.data[:32].hex(),
        }
        
        # Look for common patterns
        if self.data.startswith(b'\x48\x00'):
            bin_info['address_table_marker'] = True
        
        return bin_info
    
    def extract_identifiers(self) -> Dict:
        """Extract software and hardware identifiers"""
        identifiers = {
            'version_strings': self.extract_version_strings(),
            'all_strings': self.extract_strings(min_length=8),
            'model_info': [],
            'calibration_ids': [],
            'hardware_ids': [],
        }
        
        # Parse strings for identifiers
        for s in identifiers['all_strings']:
            # Gearbox models
            if any(model in s for model in ['DSG', 'DQ250', 'DQ381', 'DQ500', 'RM8', 'RM9']):
                identifiers['model_info'].append(s)
            
            # Calibration patterns
            if re.match(r'[0-9A-F]{2}[A-Z]{2}[0-9A-F]{4}', s):
                identifiers['calibration_ids'].append(s)
            
            # Hardware patterns
            if re.match(r'[0-9]{2}[A-Z]{2}\d{2}', s):
                identifiers['hardware_ids'].append(s)
        
        return identifiers
    
    def analyze_structure(self) -> Dict:
        """Analyze internal file structure"""
        structure = {
            'size': len(self.data),
            'entropy': self.calculate_entropy(),
            'sections': self.identify_sections(),
        }
        
        return structure
    
    def calculate_entropy(self) -> float:
        """Calculate Shannon entropy (indicates compression/encryption)"""
        if not self.data:
            return 0.0
        
        byte_freq = Counter(self.data)
        entropy = 0.0
        
        for count in byte_freq.values():
            p = count / len(self.data)
            entropy -= p * (p and -np.log2(p) or 0)
        
        return round(entropy, 2)
    
    def identify_sections(self) -> List[Dict]:
        """Identify data sections in file"""
        sections = []
        
        # Look for common section markers
        data = self.data
        
        # SGML sections
        if data.startswith(b'SGML Object File'):
            sections.append({
                'type': 'SGML_HEADER',
                'offset': 0,
                'size': 256,
                'description': 'SGML Object File header'
            })
        
        # Look for repeated patterns (likely calibration tables)
        pattern_offsets = defaultdict(int)
        for i in range(0, len(data) - 100, 512):
            chunk = data[i:i+100]
            pattern = hashlib.md5(chunk).hexdigest()
            pattern_offsets[pattern] += 1
        
        # Find data regions
        if len(data) > 0x1000:
            # First kilobyte often contains metadata
            sections.append({
                'type': 'METADATA',
                'offset': 0,
                'size': 0x1000,
                'description': 'Metadata/header region'
            })
            
            # Remaining is likely firmware data
            sections.append({
                'type': 'FIRMWARE_DATA',
                'offset': 0x1000,
                'size': len(data) - 0x1000,
                'description': 'Main firmware/calibration data'
            })
        
        return sections
    
    def full_analysis(self) -> Dict:
        """Perform complete analysis"""
        if not self.load_file():
            return {'error': 'Failed to load file'}
        
        analysis = {
            'filename': self.filename,
            'filepath': self.filepath,
            'file_header': self.analyze_header(),
            'identifiers': self.extract_identifiers(),
            'structure': self.analyze_structure(),
        }
        
        return analysis


class FlashdatenAnalyzer:
    """Analyze entire flashdaten directory"""
    
    def __init__(self, root_path: str):
        self.root_path = root_path
        self.files = []
        self.analysis_results = []
        self.software_registry = defaultdict(list)
        self.model_catalog = defaultdict(int)
        
    def scan_directory(self):
        """Scan directory for firmware files"""
        extensions = ['.frf', '.sgo', '.bin', '.odx', '.sox', '.frf-f']
        
        for ext in extensions:
            files = list(Path(self.root_path).rglob(f'*{ext}'))
            self.files.extend(files)
        
        print(f"Found {len(self.files)} firmware files")
    
    def analyze_sample(self, sample_size: int = 50):
        """Analyze sample of files"""
        import random
        
        sample = random.sample(self.files, min(sample_size, len(self.files)))
        
        for filepath in sample:
            analyzer = FirmwareAnalyzer(str(filepath))
            result = analyzer.full_analysis()
            
            if 'error' not in result:
                self.analysis_results.append(result)
                
                # Catalog software IDs
                for ver in result['identifiers']['version_strings']:
                    self.software_registry[ver].append(str(filepath))
                
                # Catalog models
                for model in result['identifiers']['model_info']:
                    self.model_catalog[model] += 1
    
    def generate_report(self) -> Dict:
        """Generate comprehensive analysis report"""
        report = {
            'total_files': len(self.files),
            'analyzed_files': len(self.analysis_results),
            'software_ids': dict(self.software_registry),
            'models_found': dict(self.model_catalog),
            'file_type_summary': self.get_file_type_summary(),
        }
        
        return report
    
    def get_file_type_summary(self) -> Dict:
        """Summarize files by type"""
        summary = defaultdict(int)
        
        for f in self.files:
            ext = f.suffix.lower()
            summary[ext] += 1
        
        return dict(summary)


def main():
    """Main analysis function"""
    root_path = r"C:\Users\katyr\Downloads\flashdaten_20220118\Flashdaten_Audi_20220118\Service42\Trade-Retail\Brand-A"
    
    print("Starting Audi Flashdaten Analysis...")
    print(f"Directory: {root_path}\n")
    
    analyzer = FlashdatenAnalyzer(root_path)
    analyzer.scan_directory()
    analyzer.analyze_sample(sample_size=50)
    
    report = analyzer.generate_report()
    
    print("\n" + "="*70)
    print("ANALYSIS REPORT")
    print("="*70)
    print(f"\nTotal Files Found: {report['total_files']}")
    print(f"Files Analyzed: {report['analyzed_files']}")
    
    print("\nFile Type Distribution:")
    for ext, count in sorted(report['file_type_summary'].items(), key=lambda x: x[1], reverse=True):
        print(f"  {ext}: {count}")
    
    print("\nSoftware IDs Found:")
    for soft_id, files in sorted(report['software_ids'].items()):
        print(f"  {soft_id}: {len(files)} files")
    
    print("\nModels Found:")
    for model, count in sorted(report['models_found'].items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"  {model}: {count} occurrences")
    
    return report


if __name__ == '__main__':
    report = main()
