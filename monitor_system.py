#!/usr/bin/env python3
"""
System performance monitoring script for file organization.
Provides insights into disk usage, file counts, and directory structure.
"""

import os
import sys
import time
from datetime import datetime

# Add script directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from utils.constants import DATA_DIR, TORBOX_DIR


def format_size(size_bytes):
    """Format bytes to human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def get_directory_stats(directory):
    """Get statistics for a directory."""
    if not os.path.exists(directory):
        return {
            'exists': False,
            'total_size': 0,
            'file_count': 0,
            'dir_count': 0,
            'subdirs': {}
        }
    
    total_size = 0
    file_count = 0
    dir_count = 0
    subdirs = {}
    
    # Get immediate subdirectories
    try:
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            
            if os.path.isdir(item_path):
                dir_count += 1
                # Calculate size of this subdirectory
                subdir_size = 0
                subdir_files = 0
                for root, dirs, files in os.walk(item_path):
                    for file in files:
                        try:
                            file_path = os.path.join(root, file)
                            file_size = os.path.getsize(file_path)
                            subdir_size += file_size
                            subdir_files += 1
                        except (OSError, PermissionError):
                            continue
                
                subdirs[item] = {
                    'size': subdir_size,
                    'files': subdir_files
                }
            elif os.path.isfile(item_path):
                try:
                    total_size += os.path.getsize(item_path)
                    file_count += 1
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError) as e:
        print(f"⚠️  Warning: Cannot access {directory}: {e}")
    
    # Add subdirectory sizes to total
    for subdir_stats in subdirs.values():
        total_size += subdir_stats['size']
        file_count += subdir_stats['files']
    
    return {
        'exists': True,
        'total_size': total_size,
        'file_count': file_count,
        'dir_count': dir_count,
        'subdirs': subdirs
    }


def identify_old_files(directory, age_hours=24):
    """Identify files older than specified hours."""
    if not os.path.exists(directory):
        return []
    
    cutoff_time = time.time() - (age_hours * 3600)
    old_files = []
    
    try:
        for root, dirs, files in os.walk(directory):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for file in files:
                if file.startswith('.'):
                    continue
                
                file_path = os.path.join(root, file)
                try:
                    mtime = os.path.getmtime(file_path)
                    if mtime < cutoff_time:
                        size = os.path.getsize(file_path)
                        age_days = (time.time() - mtime) / 86400
                        old_files.append({
                            'path': file_path,
                            'size': size,
                            'age_days': age_days
                        })
                except (OSError, PermissionError):
                    continue
    except (OSError, PermissionError) as e:
        print(f"⚠️  Warning: Cannot scan {directory}: {e}")
    
    return old_files


def identify_extraction_directories(directory):
    """Identify potential orphaned extraction directories."""
    if not os.path.exists(directory):
        return []
    
    extraction_dirs = []
    
    try:
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            
            if (os.path.isdir(item_path) and 
                not item.startswith('.') and 
                item != 'torbox' and
                ('extract' in item.lower() or '_files' in item or len(item) > 20)):
                
                # Calculate directory info
                dir_size = 0
                file_count = 0
                latest_mtime = 0
                
                for root, dirs, files in os.walk(item_path):
                    for file in files:
                        try:
                            file_path = os.path.join(root, file)
                            dir_size += os.path.getsize(file_path)
                            file_count += 1
                            latest_mtime = max(latest_mtime, os.path.getmtime(file_path))
                        except (OSError, PermissionError):
                            continue
                
                age_hours = (time.time() - latest_mtime) / 3600 if latest_mtime > 0 else 0
                
                extraction_dirs.append({
                    'name': item,
                    'path': item_path,
                    'size': dir_size,
                    'files': file_count,
                    'age_hours': age_hours
                })
    except (OSError, PermissionError) as e:
        print(f"⚠️  Warning: Cannot scan {directory}: {e}")
    
    return extraction_dirs


def generate_report():
    """Generate a comprehensive monitoring report."""
    print("=" * 80)
    print(f"FILE ORGANIZATION PERFORMANCE REPORT")
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Overall DATA_DIR stats
    print(f"\n📊 DATA DIRECTORY: {DATA_DIR}")
    print("-" * 80)
    
    data_stats = get_directory_stats(DATA_DIR)
    
    if not data_stats['exists']:
        print("❌ DATA_DIR does not exist!")
        return
    
    print(f"Total Size:       {format_size(data_stats['total_size'])}")
    print(f"Total Files:      {data_stats['file_count']}")
    print(f"Subdirectories:   {data_stats['dir_count']}")
    
    # Subdirectory breakdown
    if data_stats['subdirs']:
        print(f"\n📁 Subdirectory Breakdown:")
        print(f"{'Directory':<30} {'Size':<15} {'Files':<10}")
        print("-" * 80)
        
        # Sort by size (largest first)
        sorted_subdirs = sorted(
            data_stats['subdirs'].items(),
            key=lambda x: x[1]['size'],
            reverse=True
        )
        
        for subdir, stats in sorted_subdirs:
            print(f"{subdir:<30} {format_size(stats['size']):<15} {stats['files']:<10}")
    
    # TORBOX_DIR stats
    print(f"\n📦 TORBOX DIRECTORY: {TORBOX_DIR}")
    print("-" * 80)
    
    torbox_stats = get_directory_stats(TORBOX_DIR)
    
    if torbox_stats['exists']:
        print(f"Total Size:       {format_size(torbox_stats['total_size'])}")
        print(f"Total Files:      {torbox_stats['file_count']}")
        print(f"Subdirectories:   {torbox_stats['dir_count']}")
    else:
        print("⚠️  TORBOX_DIR does not exist!")
    
    # Old files analysis
    print(f"\n🕐 OLD FILES ANALYSIS (>24 hours)")
    print("-" * 80)
    
    old_files = identify_old_files(DATA_DIR, age_hours=24)
    
    if old_files:
        total_old_size = sum(f['size'] for f in old_files)
        print(f"Old Files:        {len(old_files)}")
        print(f"Total Size:       {format_size(total_old_size)}")
        print(f"Avg Age:          {sum(f['age_days'] for f in old_files) / len(old_files):.1f} days")
        
        # Show top 5 largest old files
        old_files.sort(key=lambda x: x['size'], reverse=True)
        print(f"\n🔍 Top 5 Largest Old Files:")
        for i, file_info in enumerate(old_files[:5], 1):
            rel_path = os.path.relpath(file_info['path'], DATA_DIR)
            print(f"  {i}. {rel_path}")
            print(f"     Size: {format_size(file_info['size'])}, Age: {file_info['age_days']:.1f} days")
    else:
        print("✅ No old files found")
    
    # Extraction directories analysis
    print(f"\n📂 EXTRACTION DIRECTORIES ANALYSIS")
    print("-" * 80)
    
    extraction_dirs = identify_extraction_directories(DATA_DIR)
    
    if extraction_dirs:
        total_extraction_size = sum(d['size'] for d in extraction_dirs)
        print(f"Extraction Dirs:  {len(extraction_dirs)}")
        print(f"Total Size:       {format_size(total_extraction_size)}")
        
        print(f"\n{'Directory':<40} {'Size':<15} {'Age (hrs)':<12}")
        print("-" * 80)
        
        # Sort by age (oldest first)
        extraction_dirs.sort(key=lambda x: x['age_hours'], reverse=True)
        
        for dir_info in extraction_dirs:
            print(f"{dir_info['name']:<40} {format_size(dir_info['size']):<15} {dir_info['age_hours']:.1f}")
        
        # Identify candidates for cleanup
        orphaned = [d for d in extraction_dirs if d['age_hours'] > 1]
        if orphaned:
            orphaned_size = sum(d['size'] for d in orphaned)
            print(f"\n⚠️  {len(orphaned)} directories eligible for cleanup (>1 hour old)")
            print(f"   Potential space recovery: {format_size(orphaned_size)}")
    else:
        print("✅ No extraction directories found")
    
    # Recommendations
    print(f"\n💡 RECOMMENDATIONS")
    print("-" * 80)
    
    recommendations = []
    
    if old_files:
        old_size = sum(f['size'] for f in old_files)
        if old_size > 100 * 1024 * 1024:  # > 100MB
            recommendations.append(
                f"🧹 Run /cleanup to remove {len(old_files)} old files and recover {format_size(old_size)}"
            )
    
    if extraction_dirs:
        orphaned = [d for d in extraction_dirs if d['age_hours'] > 1]
        if orphaned:
            orphaned_size = sum(d['size'] for d in orphaned)
            if orphaned_size > 50 * 1024 * 1024:  # > 50MB
                recommendations.append(
                    f"🧹 Run /cleanup-orphans to remove {len(orphaned)} directories and recover {format_size(orphaned_size)}"
                )
    
    if data_stats['total_size'] > 10 * 1024 * 1024 * 1024:  # > 10GB
        recommendations.append(
            "⚠️  Data directory is large (>10GB). Consider regular cleanup maintenance."
        )
    
    if not recommendations:
        recommendations.append("✅ File organization looks good! No immediate actions needed.")
    
    for rec in recommendations:
        print(f"  {rec}")
    
    print("\n" + "=" * 80)


def main():
    """Main entry point."""
    try:
        generate_report()
        return 0
    except Exception as e:
        print(f"\n❌ Error generating report: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
