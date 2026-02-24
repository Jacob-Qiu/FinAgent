import os

def list_reports(directory):
    """
    Lists all PDF files in the specified directory.
    """
    print(f"Scanning directory: {directory}\n")
    
    if not os.path.exists(directory):
        print(f"Error: Directory '{directory}' not found.")
        return

    files = [f for f in os.listdir(directory) if f.lower().endswith('.pdf')]
    files.sort()  # Sort alphabetically

    if not files:
        print("No PDF files found.")
    else:
        print(f"Found {len(files)} report(s):")
        print("-" * 60)
        for i, filename in enumerate(files, 1):
            print(f"{i}. {filename}")
        print("-" * 60)

if __name__ == "__main__":
    target_dir = "/Users/maowenyuan/Desktop/科技/"
    list_reports(target_dir)
