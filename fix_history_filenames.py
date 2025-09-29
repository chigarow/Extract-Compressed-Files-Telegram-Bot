#!/usr/bin/env python3

import os
import re
from pathlib import Path

def fix_history_filenames():
    history_dir = Path("/Users/gradito.tunggulcahyo/Documents/Script/ExtractCompressedFiles/.history")
    
    if not history_dir.exists():
        print(f"Directory {history_dir} does not exist.")
        return
    
    # Get all .md files in the directory
    md_files = list(history_dir.glob("*.md"))
    
    if not md_files:
        print("No .md files found in the directory.")
        return
    
    print(f"Found {len(md_files)} files to fix:")
    
    # Regular expression to match the problematic pattern
    pattern = re.compile(r'^(\d{4}-\d{2}-\d{2})_(\d{2}:\d{2}:\d{2})_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}_.+\.md)$')
    
    for file_path in md_files:
        filename = file_path.name
        
        # Check if the filename matches the problematic pattern
        match = pattern.match(filename)
        if match:
            # Extract the correct part (the part after the timestamp)
            corrected_filename = match.group(3)
            new_file_path = file_path.parent / corrected_filename
            
            # Rename the file
            try:
                # If the corrected filename already exists, we need to handle that
                if new_file_path.exists():
                    print(f"Skipping {filename} - corrected name already exists")
                else:
                    file_path.rename(new_file_path)
                    print(f"Fixed: {filename} -> {corrected_filename}")
            except Exception as e:
                print(f"Error fixing {filename}: {e}")
        else:
            print(f"Already correct: {filename}")

if __name__ == "__main__":
    fix_history_filenames()