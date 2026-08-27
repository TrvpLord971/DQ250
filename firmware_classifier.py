#!/usr/bin/env python3
"""
Firmware File Classification Tool
Identifies whether files are gearbox (DSG/DQ250/DQ381/DQ500), engine, ABS, or other systems
Uses part number database and filename patterns
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional


class FirmwareClassifier:
    """Classify firmware files by system type and variant"""
    
    # Known Audi/VW part numbers and their meanings
    PART_NUMBER_DATABASE = {
        # TRANSMISSION/GEARBOX
        '03C906016': {'system': 'Transmission', 'type': 'DSG 6-Speed (DQ250)', 'platform': 'MQB', 'variants': []},
        '022906032': {'system': 'Transmission', 'type': 'Transmission Module (DQ250/DQ381/DQ500)', 'platform': 'Multi', 'variants': ['6-speed', '7-speed']},
        '0AM906': {'system': 'Transmission', 'type': 'DCT (Dual Clutch Transmission)', 'platform': 'Various', 'variants': []},
        '0BX906': {'system': 'Transmission', 'type': 'Multi-Speed Automatic', 'platform': 'Various', 'variants': []},
        '0CK906': {'system': 'Transmission', 'type': 'Transmission Control Module', 'platform': 'Various', 'variants': []},
        '0CW300047': {'system': 'Transmission', 'type': 'Hybrid Transmission Control', 'platform': 'Hybrid', 'variants': []},
        
        # ENGINE ECU
        '03L906022': {'system': 'Engine ECU', 'type': '4-cylinder TSI/TFSI', 'platform': 'B8.5/B9 (A4/A6)', 'variants': ['1.8T', '2.0T', '1.4T']},
        '03G906016': {'system': 'Engine ECU', 'type': '4-cylinder TSI', 'platform': 'MQB (A3/Golf)', 'variants': []},
        '04L906021': {'system': 'Engine ECU', 'type': '4-cylinder TFSI', 'platform': '8V (A3 2012+)', 'variants': []},
        '04L906026': {'system': 'Engine ECU', 'type': '4-cylinder TFSI', 'platform': '8V', 'variants': []},
        '03L906019': {'system': 'Engine ECU', 'type': 'Multi-cylinder TFSI', 'platform': 'B8.5/B9', 'variants': []},
        '03L906023': {'system': 'Engine ECU', 'type': 'Multi-cylinder TFSI', 'platform': 'B8.5/B9', 'variants': []},
        '04E906016': {'system': 'Engine ECU', 'type': '2.0L TFSI Family', 'platform': 'MQB', 'variants': []},
        '06D906': {'system': 'Engine ECU', 'type': 'VW Group Engine', 'platform': 'Various', 'variants': []},
        '04C906': {'system': 'Engine ECU', 'type': 'Audi Engine', 'platform': 'Various', 'variants': []},
        '06A906033': {'system': 'Engine ECU', 'type': 'Legacy Engine', 'platform': 'Pre-MQB', 'variants': []},
        '06F906': {'system': 'Engine ECU', 'type': 'Engine Control', 'platform': 'Various', 'variants': []},
        
        # BRAKING/STABILITY
        '8K0614517': {'system': 'ABS/ESP', 'type': 'ABS/ESP Module', 'platform': 'Audi', 'variants': []},
        '8K0907379': {'system': 'ABS/ESP', 'type': 'ABS/ESP Control', 'platform': 'Audi', 'variants': []},
        
        # ELECTRIC/COMPONENTS
        '9J1915539': {'system': 'Electrical Component', 'type': 'Booster/Starter', 'platform': 'Various', 'variants': []},
        
        # OTHER
        '03C906022': {'system': 'Engine ECU', 'type': 'Legacy Engine ECU', 'platform': 'B6/B7', 'variants': []},
        '03C906056': {'system': 'Engine ECU', 'type': 'Legacy Engine', 'platform': 'Pre-MQB', 'variants': []},
        '03C997022': {'system': 'Engine ECU', 'type': 'Legacy Engine', 'platform': 'B6/B7', 'variants': []},
    }
    
    # Keyword patterns for system identification
    KEYWORD_PATTERNS = {
        'Transmission': [
            r'DQ25[0-9]', r'DQ38[0-9]', r'DQ50[0-9]',  # DQ transmission codes
            r'DSG', r'getriebe', r'transmission', r'gearbox',
            r'0AM906', r'0BX906', r'0CK906', r'022906032', r'03C906016',
            r'multi.*speed', r'dual.*clutch', r'DCT',
        ],
        'Engine': [
            r'03L906', r'03G906', r'04L906', r'04E906', r'06[DAF]906',
            r'TFSI', r'TSI', r'TDI', r'motor', r'engine', r'ECU',
            r'ignition', r'fuel', r'intake',
        ],
        'ABS/ESP': [
            r'ABS', r'ESP', r'8K0614', r'8K0907', r'stability', r'braking',
            r'antilock', r'dynamic.*stability',
        ],
        'Other': [
            r'gateway', r'comfort', r'instrument', r'infotainment',
            r'HVAC', r'climate', r'BCM', r'TCU',
        ]
    }
    
    def __init__(self):
        self.classification_cache = {}
    
    def extract_part_number(self, filename: str) -> Optional[str]:
        """Extract part number from filename"""
        # Pattern: 2-3 letters + 2-3 digits + 2-4 letters + 2-6 digits
        patterns = [
            r'([0-9A-Z]{2,3}[A-Z]{0,2}\d{6})',  # e.g., 03C906016
            r'([0-9]{2}[A-Z]{2}\d{2,6})',  # e.g., 022906032
            r'([A-Z]{2}\d{1}[A-Z]{2}\d{2,6})',  # e.g., FL_03C906016
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                return match.group(1)
        
        return None
    
    def classify_by_part_number(self, part_number: str) -> Optional[Dict]:
        """Look up part number in database"""
        # Exact match
        if part_number in self.PART_NUMBER_DATABASE:
            return self.PART_NUMBER_DATABASE[part_number]
        
        # Prefix match (e.g., 03L906 matches any 03L906xxx)
        for db_part, info in self.PART_NUMBER_DATABASE.items():
            if part_number.startswith(db_part[:8]):  # Match first 8 chars
                return info
        
        return None
    
    def classify_by_keywords(self, filename: str) -> Optional[str]:
        """Classify by keyword patterns"""
        filename_lower = filename.lower()
        
        for system, patterns in self.KEYWORD_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, filename_lower, re.IGNORECASE):
                    return system
        
        return None
    
    def classify_file(self, filepath: str) -> Dict:
        """
        Classify a firmware file
        
        Returns:
        {
            'filename': str,
            'system': str,  # Transmission, Engine, ABS/ESP, Other, Unknown
            'type': str,  # Specific component type
            'platform': str,  # MQB, B8.5, etc.
            'part_number': str,
            'confidence': str,  # High, Medium, Low
            'variants': list,  # Known variants
            'file_format': str,  # FRF, SGO, BIN, etc.
        }
        """
        filename = Path(filepath).name
        file_ext = Path(filepath).suffix.lower()
        
        result = {
            'filename': filename,
            'filepath': filepath,
            'file_format': file_ext[1:] if file_ext else 'unknown',
            'system': None,
            'type': None,
            'platform': None,
            'part_number': None,
            'confidence': 'Low',
            'variants': [],
            'notes': []
        }
        
        # Try to extract part number
        part_number = self.extract_part_number(filename)
        
        if part_number:
            result['part_number'] = part_number
            part_info = self.classify_by_part_number(part_number)
            
            if part_info:
                result['system'] = part_info['system']
                result['type'] = part_info['type']
                result['platform'] = part_info['platform']
                result['variants'] = part_info.get('variants', [])
                result['confidence'] = 'High'
                return result
        
        # Fallback to keyword matching
        keyword_system = self.classify_by_keywords(filename)
        
        if keyword_system:
            result['system'] = keyword_system
            result['confidence'] = 'Medium'
            
            # Try to get more details
            if keyword_system == 'Transmission':
                result['type'] = 'Transmission/Gearbox (Specific type unknown)'
            elif keyword_system == 'Engine':
                result['type'] = 'Engine ECU (Specific type unknown)'
            elif keyword_system == 'ABS/ESP':
                result['type'] = 'Stability Control System'
            
            return result
        
        # Unknown
        result['system'] = 'Unknown'
        result['type'] = 'Unable to classify'
        result['confidence'] = 'Low'
        result['notes'].append('File classification failed - unknown part number or keywords')
        
        return result
    
    def classify_directory(self, directory: str) -> Dict:
        """Classify all firmware files in a directory"""
        results = {
            'total_files': 0,
            'by_system': {},
            'by_platform': {},
            'by_format': {},
            'files': []
        }
        
        extensions = ['.frf', '.sgo', '.bin', '.odx', '.sox', '.frf-f']
        
        for ext in extensions:
            for filepath in Path(directory).rglob(f'*{ext}'):
                classification = self.classify_file(str(filepath))
                results['files'].append(classification)
                results['total_files'] += 1
                
                # Aggregate by system
                system = classification['system']
                if system not in results['by_system']:
                    results['by_system'][system] = 0
                results['by_system'][system] += 1
                
                # Aggregate by platform
                platform = classification['platform']
                if platform not in results['by_platform']:
                    results['by_platform'][platform] = 0
                results['by_platform'][platform] += 1
                
                # Aggregate by format
                fmt = classification['file_format']
                if fmt not in results['by_format']:
                    results['by_format'][fmt] = 0
                results['by_format'][fmt] += 1
        
        return results


def print_classification_report(classification: Dict):
    """Pretty-print a classification result"""
    print(f"\n{'='*70}")
    print(f"File: {classification['filename']}")
    print(f"{'='*70}")
    print(f"Format: {classification['file_format'].upper()}")
    print(f"Part Number: {classification['part_number'] or 'Not found'}")
    print(f"\nSystem: {classification['system']}")
    print(f"Type: {classification['type']}")
    print(f"Platform: {classification['platform']}")
    print(f"Confidence: {classification['confidence']}")
    
    if classification['variants']:
        print(f"Known Variants: {', '.join(classification['variants'])}")
    
    if classification['notes']:
        print(f"\nNotes:")
        for note in classification['notes']:
            print(f"  - {note}")


def main():
    """Main CLI interface"""
    import sys
    
    classifier = FirmwareClassifier()
    
    # Example 1: Single file classification
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        result = classifier.classify_file(filepath)
        print_classification_report(result)
    else:
        # Example 2: Directory analysis
        test_dir = r"C:\Users\katyr\Downloads\flashdaten_20220118\Flashdaten_Audi_20220118\Service42\Trade-Retail\Brand-A"
        
        print("Audi Flashdaten Firmware Classifier")
        print("="*70)
        print(f"Analyzing directory: {test_dir}")
        print("This may take a moment...\n")
        
        results = classifier.classify_directory(test_dir)
        
        print(f"Total Files Analyzed: {results['total_files']}")
        
        print(f"\nBy System Type:")
        for system, count in sorted(results['by_system'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {system}: {count} files ({100*count/results['total_files']:.1f}%)")
        
        print(f"\nBy Platform:")
        for platform, count in sorted(results['by_platform'].items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                print(f"  {platform}: {count} files ({100*count/results['total_files']:.1f}%)")
        
        print(f"\nBy Format:")
        for fmt, count in sorted(results['by_format'].items(), key=lambda x: x[1], reverse=True):
            print(f"  .{fmt}: {count} files ({100*count/results['total_files']:.1f}%)")
        
        # Show Transmission files
        print(f"\n{'='*70}")
        print("TRANSMISSION FILES (Gearbox/DSG/DQ250/DQ381/DQ500):")
        print(f"{'='*70}")
        trans_count = 0
        for file_info in results['files']:
            if 'Transmission' in (file_info['system'] or ''):
                trans_count += 1
                if trans_count <= 30:  # Show first 30
                    print(f"  {file_info['filename']:<50} | {file_info['type']:<40} | Conf: {file_info['confidence']}")
        print(f"\nTotal: {sum(1 for f in results['files'] if 'Transmission' in (f['system'] or ''))} transmission files")


if __name__ == '__main__':
    main()
