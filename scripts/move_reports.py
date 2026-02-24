import os
import shutil

def move_reports():
    source_dir = "/Users/maowenyuan/Desktop/科技/"
    base_target_dir = "/Users/maowenyuan/FinAgent/data/reports/"
    
    # Define categories and their file indices (1-based from list_reports.py output)
    categories = {
        "01_AI_Computing": [5, 7, 8, 9, 10, 13, 14, 17, 20, 21, 31, 32, 33, 44, 46, 47, 49, 50, 51, 54],
        "02_Energy_Power": [15, 16, 36, 37, 38, 39, 40, 41, 42, 43, 45],
        "03_Future_Tech": [11, 12, 23, 24, 25, 26, 27, 28, 29, 30, 35, 52, 53],
        "04_Macro_Strategy": [2, 3, 19, 48, 55, 56, 57],
        "05_Resources_Industry": [1, 4, 6, 18, 22, 34]
    }
    
    # Get list of files in alphabetical order to match the indices
    if not os.path.exists(source_dir):
        print(f"Error: Source directory '{source_dir}' not found.")
        return

    files = [f for f in os.listdir(source_dir) if f.lower().endswith('.pdf')]
    files.sort()
    
    # Verify file count matches expectations roughly (we have indices up to 57)
    if len(files) < 57:
        print(f"Warning: Found only {len(files)} files, but indices go up to 57. Indices might be mismatched.")
    
    # Create target directories
    for category in categories:
        target_path = os.path.join(base_target_dir, category)
        os.makedirs(target_path, exist_ok=True)
        print(f"Created/Verified directory: {target_path}")
        
    print("-" * 60)
    
    # Execute Moves
    moved_count = 0
    errors = 0
    
    for category, indices in categories.items():
        target_path = os.path.join(base_target_dir, category)
        print(f"\nProcessing {category}...")
        
        for index in indices:
            # Adjust 1-based index to 0-based
            list_idx = index - 1
            
            if list_idx < 0 or list_idx >= len(files):
                print(f"  [Error] Index {index} is out of range (Total files: {len(files)})")
                errors += 1
                continue
                
            filename = files[list_idx]
            src_file = os.path.join(source_dir, filename)
            dst_file = os.path.join(target_path, filename)
            
            try:
                # Use shutil.move to move files
                # Check if file exists first (it might have been moved already if indices duplicate)
                if not os.path.exists(src_file):
                    print(f"  [Skip] File not found (already moved?): {filename}")
                    continue
                    
                shutil.move(src_file, dst_file)
                print(f"  [Moved] {filename}")
                moved_count += 1
            except Exception as e:
                print(f"  [Error] Failed to move {filename}: {e}")
                errors += 1

    print("-" * 60)
    print(f"Move Complete. Moved: {moved_count}, Errors: {errors}")

if __name__ == "__main__":
    move_reports()
