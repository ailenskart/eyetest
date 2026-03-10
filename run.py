#!/usr/bin/env python3
"""
Main execution script for eye test engine.
Processes curated conversation CSVs and annotates with phase information.
"""
import argparse
from pathlib import Path
from typing import List

from .core.context import RowContext
from .core.state_machine import StateMachine
from .io.inputs import load_csv, load_directory
from .io.outputs import write_annotated_csv, generate_summary, write_summary_report


def process_session(rows: List[RowContext], state_machine: StateMachine) -> List[RowContext]:
    """
    Process a single test session and annotate with phases.
    
    Args:
        rows: List of RowContext objects
        state_machine: StateMachine instance
    
    Returns:
        List of RowContext objects with phase annotations
    """
    annotated_rows = []
    
    for i, row in enumerate(rows):
        prev = rows[i - 1] if i > 0 else None
        nxt = rows[i + 1] if i + 1 < len(rows) else None
        
        # Determine phase
        phase_id = state_machine.process_row(row, prev, nxt)
        phase_name = state_machine.get_phase_name(phase_id)
        
        # Annotate row
        row.phase_id = phase_id
        row.phase_name = phase_name
        
        annotated_rows.append(row)
    
    return annotated_rows


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(description="Eye Test Engine - Phase Annotation")
    parser.add_argument("input", type=str, help="Input CSV file or directory")
    parser.add_argument("--output", type=str, help="Output directory (default: eye_test_output)")
    parser.add_argument("--summary", action="store_true", help="Generate summary reports")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_dir = Path(args.output) if args.output else Path("eye_test_output")
    output_dir.mkdir(exist_ok=True, parents=True)
    
    # Initialize state machine
    state_machine = StateMachine()
    
    # Process input
    if input_path.is_file():
        # Single file
        if args.verbose:
            print(f"Processing file: {input_path.name}")
        
        rows = load_csv(input_path)
        annotated_rows = process_session(rows, state_machine)
        
        output_path = output_dir / f"annotated_{input_path.name}"
        write_annotated_csv(annotated_rows, output_path)
        
        if args.summary:
            summary = generate_summary(annotated_rows)
            summary_path = output_dir / f"summary_{input_path.stem}.txt"
            write_summary_report(summary, summary_path)
        
        print(f"✓ Processed {len(annotated_rows)} rows")
        print(f"  Output: {output_path}")
        if args.summary:
            print(f"  Summary: {summary_path}")
    
    elif input_path.is_dir():
        # Directory
        sessions = load_directory(input_path)
        
        print(f"Processing {len(sessions)} files from {input_path}")
        
        for filename, rows in sessions.items():
            if args.verbose:
                print(f"  Processing: {filename}")
            
            # Reset state machine for each session
            state_machine = StateMachine()
            
            annotated_rows = process_session(rows, state_machine)
            
            output_path = output_dir / f"annotated_{filename}"
            write_annotated_csv(annotated_rows, output_path)
            
            if args.summary:
                summary = generate_summary(annotated_rows)
                summary_path = output_dir / f"summary_{Path(filename).stem}.txt"
                write_summary_report(summary, summary_path)
            
            if args.verbose:
                print(f"    ✓ {len(annotated_rows)} rows")
        
        print(f"\n✓ Processed {len(sessions)} sessions")
        print(f"  Output directory: {output_dir}")
    
    else:
        print(f"Error: {input_path} is not a valid file or directory")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
