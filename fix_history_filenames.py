#!/usr/bin/env python3

import os
import re
import sys
from pathlib import Path
from datetime import datetime

def fix_history_filenames():
    """
    Scans a directory for .md files and renames them to a consistent
    YYYY-MM-DD_HH-MM-SS_description.md format.
    Accepts an optional command-line argument for the target directory.
    Defaults to './.history' if no argument is given.
    """
    # Check for a command-line argument for the directory path
    if len(sys.argv) > 1:
        # Use the provided argument as the path
        history_dir_path = sys.argv[1]
    else:
        # Default to '.history' in the current working directory
        history_dir_path = ".history"

    history_dir = Path(history_dir_path)
    
    if not history_dir.exists():
        print(f"Error: Directory '{history_dir}' does not exist.")
        return
    
    # Get all .md files in the directory
    md_files = list(history_dir.glob("*.md"))
    
    if not md_files:
        print(f"No .md files found in '{history_dir}'.")
        return
    
    print(f"Found {len(md_files)} files to potentially fix in '{history_dir}':")
    
    # Regex patterns for various filename formats
    proper_format_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_.+\.md$')
    problematic_format_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2})_(\d{2}:\d{2}:\d{2})_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_.+\.md)$')
    partial_time_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2})_([0-2][0-9][0-5][0-9])_([^.]+\.md)$')
    date_without_time_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2})_([^0-9].*\.md)$')
    
    for file_path in md_files:
        filename = file_path.name
        
        # 1. Check if it already has the proper format
        if proper_format_pattern.match(filename):
            print(f"Correct format: {filename}")
            continue
        
        # 2. Check for the problematic duplicate timestamp format
        match = problematic_format_pattern.match(filename)
        if match:
            corrected_filename = match.group(3)
            new_file_path = file_path.parent / corrected_filename
            try:
                if new_file_path.exists():
                    print(f"Skipping {filename} - corrected name already exists")
                else:
                    file_path.rename(new_file_path)
                    print(f"Fixed (removed prefix): {filename} -> {corrected_filename}")
            except Exception as e:
                print(f"Error fixing {filename}: {e}")
            continue # Move to the next file

        # 3. Check for date with partial time format (HHMM)
        match = partial_time_pattern.match(filename)
        if match:
            date_part, time_part, description = match.groups()
            hour, minute = time_part[:2], time_part[2:]
            
            corrected_filename = f"{date_part}_{hour}-{minute}-00_{description}"
            new_file_path = file_path.parent / corrected_filename
            try:
                if new_file_path.exists():
                    print(f"Skipping {filename} - corrected name already exists")
                else:
                    file_path.rename(new_file_path)
                    print(f"Fixed (added seconds): {filename} -> {corrected_filename}")
            except Exception as e:
                print(f"Error fixing {filename}: {e}")
            continue # Move to the next file

        # 4. Check for date without any time format
        match = date_without_time_pattern.match(filename)
        if match:
            date_part, description = match.groups()
            
            corrected_filename = f"{date_part}_00-00-00_{description}"
            new_file_path = file_path.parent / corrected_filename
            try:
                if new_file_path.exists():
                    print(f"Skipping {filename} - corrected name already exists")
                else:
                    file_path.rename(new_file_path)
                    print(f"Fixed (added default time): {filename} -> {corrected_filename}")
            except Exception as e:
                print(f"Error fixing {filename}: {e}")
            continue # Move to the next file

        # 5. Handle files with no date prefix at all
        # Use the file's modification time to create a timestamp
        try:
            mod_time = file_path.stat().st_mtime
            dt_object = datetime.fromtimestamp(mod_time)
            formatted_date = dt_object.strftime('%Y-%m-%d_%H-%M-%S')
            
            corrected_filename = f"{formatted_date}_{filename}"
            new_file_path = file_path.parent / corrected_filename

            if new_file_path.exists():
                print(f"Skipping {filename} - corrected name already exists")
            else:
                file_path.rename(new_file_path)
                print(f"Fixed (added timestamp): {filename} -> {corrected_filename}")
        except Exception as e:
            print(f"Error adding timestamp to {filename}: {e}")

if __name__ == "__main__":
    fix_history_filenames()

