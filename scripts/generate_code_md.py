import os

def generate_tree(dir_path, ignore_dirs=None, prefix=""):
    """Generates a text representation of the folder structure."""
    if ignore_dirs is None:
        ignore_dirs = {'.git', '__pycache__', 'venv', '.venv', 'env', 'node_modules', '.idea', '.vscode', 'build', 'dist'}
    
    tree_str = ""
    try:
        items = os.listdir(dir_path)
    except PermissionError:
        return ""

    items.sort()
    # Filter out ignored directories
    items = [item for item in items if item not in ignore_dirs]

    for i, item in enumerate(items):
        path = os.path.join(dir_path, item)
        is_last = i == (len(items) - 1)
        if is_last:
            tree_str += f"{prefix}└── {item}\n"
            new_prefix = prefix + "    "
        else:
            tree_str += f"{prefix}├── {item}\n"
            new_prefix = prefix + "│   "
            
        if os.path.isdir(path):
            tree_str += generate_tree(path, ignore_dirs, new_prefix)
            
    return tree_str

def generate_markdown(output_file="codebase_summary.md", source_dir=".", ignore_dirs=None, ignore_exts=None):
    """Creates a markdown file with the folder structure and content of all files."""
    if ignore_dirs is None:
        ignore_dirs = {'.git', '__pycache__', 'venv', '.venv', 'env', 'node_modules', '.idea', '.vscode', 'build', 'dist'}
    
    # Common binary and non-text files to ignore
    if ignore_exts is None:
        ignore_exts = {'.pyc', '.pyo', '.pyd', '.so', '.dll', '.exe', '.bin', 
                       '.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', 
                       '.zip', '.tar', '.gz', '.mp4', '.mp3', '.sqlite3'}
        
    print(f"Generating {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as outfile:
        outfile.write("# Codebase Structure\n\n")
        outfile.write("```text\n")
        outfile.write(f"{os.path.basename(os.path.abspath(source_dir))}/\n")
        outfile.write(generate_tree(source_dir, ignore_dirs))
        outfile.write("```\n\n")
        
        outfile.write("# Code Files\n\n")
        
        for root, dirs, files in os.walk(source_dir):
            # Modify dirs in-place to skip ignored directories in os.walk
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                # Skip binary files, images, or the output file itself
                if ext in ignore_exts or file == output_file or file == os.path.basename(__file__):
                    continue
                    
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, source_dir)
                
                outfile.write(f"## `{rel_path}`\n\n")
                
                # Determine language for markdown block
                lang = ext[1:] if ext else "text"
                if lang == "txt": lang = "text"
                
                outfile.write(f"```{lang}\n")
                try:
                    with open(file_path, 'r', encoding='utf-8') as infile:
                        content = infile.read()
                        outfile.write(content)
                        # Ensure there is a newline at the end of the content before closing the code block
                        if content and not content.endswith('\n'):
                            outfile.write('\n')
                except UnicodeDecodeError:
                    outfile.write(f"// File appears to be binary or has an unsupported encoding and could not be read.\n")
                except Exception as e:
                    outfile.write(f"// Error reading file: {e}\n")
                outfile.write("```\n\n")
                
    print(f"Successfully generated {output_file}!")

if __name__ == "__main__":
    generate_markdown()
    
