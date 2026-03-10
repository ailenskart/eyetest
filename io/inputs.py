"""
Input handling: Load and parse CSV files.
"""
import csv
from pathlib import Path
from typing import List
from ..core.context import RowContext, parse_row


def load_csv(csv_path: Path) -> List[RowContext]:
    """
    Load a CSV file and parse into RowContext objects.
    
    Args:
        csv_path: Path to CSV file
    
    Returns:
        List of RowContext objects
    """
    rows = []
    
    with csv_path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row_dict in reader:
            try:
                row = parse_row(row_dict)
                rows.append(row)
            except Exception as e:
                print(f"Warning: Failed to parse row {len(rows) + 1}: {e}")
                continue
    
    return rows


def load_directory(dir_path: Path, pattern: str = "*.csv") -> dict:
    """
    Load all CSV files from a directory.
    
    Args:
        dir_path: Path to directory
        pattern: Glob pattern for CSV files
    
    Returns:
        Dict mapping filename to List[RowContext]
    """
    results = {}
    
    for csv_path in sorted(dir_path.glob(pattern)):
        try:
            rows = load_csv(csv_path)
            results[csv_path.name] = rows
        except Exception as e:
            print(f"Warning: Failed to load {csv_path.name}: {e}")
            continue
    
    return results
