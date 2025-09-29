#!/usr/bin/env python3

import os
import time
from pathlib import Path

def rename_history_files():
    history_dir = Path("/Users/gradito.tunggulcahyo/Documents/Script/ExtractCompressedFiles/.history")
    
    if not history_dir.exists():
        print(f"Directory {history_dir} does not exist.")
        return
    
    # Get all .md files in the directory
    md_files = list(history_dir.glob("*.md"))
    
    if not md_files:
        print("No .md files found in the directory.")
        return
    
    print(f"Found {len(md_files)} files to rename:")
    
    for file_path in md_files:
        # Get the modification time
        mod_time = os.path.getmtime(file_path)
        # Convert to struct_time
        time_struct = time.localtime(mod_time)
        # Format as HH:MM:SS
        time_str = time.strftime("%H:%M:%S", time_struct)
        # Format date as YYYY-MM-DD
        date_str = time.strftime("%Y-%m-%d", time_struct)
        
        # Get the original filename without extension
        stem = file_path.stem
        suffix = file_path.suffix
        
        # Create new filename with time prefix
        new_filename = f"{date_str}_{time_str}_{stem}{suffix}"
        new_file_path = file_path.parent / new_filename
        
        # Rename the file
        try:
            file_path.rename(new_file_path)
            print(f"Renamed: {file_path.name} -> {new_filename}")
        except Exception as e:
            print(f"Error renaming {file_path.name}: {e}")

if __name__ == "__main__":
    rename_history_files()