import subprocess
import sys
import os
import shutil

def build():
    """Build a standalone executable for WuwaCalc."""
    print("=" * 60)
    print("WuwaCalc Standalone Executable Build Tool")
    print("=" * 60)
    
    # Check for Tesseract
    tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    tesseract_available = os.path.exists(tesseract_path)
    
    if tesseract_available:
        print("\n[OK] Tesseract OCR detected.")
        print(f"    Path: {tesseract_path}")
        print("    → Building with Tesseract included.")
    else:
        print("\n[!] Tesseract OCR not found.")
        print(f"    Path: {tesseract_path}")
        print("    → Building without Tesseract (OCR function will not be available).")
    
    # Clean up existing builds
    print("\n[1/3] Cleaning up existing build folders...")
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            print(f"  - Deleting {folder} folder...")
            shutil.rmtree(folder)
    
    # Build with PyInstaller
    print("\n[2/3] Building with PyInstaller...")
    print("  ※ This process may take several minutes.")
    
    # Build using spec file
    cmd = ["pyinstaller", "--clean", "wuwacalc.spec"]
    
    print(f"\nExecuting command: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n" + "=" * 60)
        print("[OK] Build successful!")
        print("=" * 60)
        exe_path = os.path.abspath('dist/wuwacalc17.exe')
        print(f"\nExecutable: {exe_path}")
        print(f"File size: {os.path.getsize(exe_path) / (1024*1024):.1f} MB")
        print("\n[3/3] Copying additional files...")
        
        # Copy necessary folders to dist
        dist_dir = "dist"
        if os.path.isdir("character_settings_jsons"):
            dest = os.path.join(dist_dir, "character_settings_jsons")
            if os.path.exists(dest):
                shutil.rmtree(dest)
            shutil.copytree("character_settings_jsons", dest)
            print(f"  [OK] Copied character_settings_jsons.")
        
        # Copy README.md and help
        if os.path.exists("README.html"):
            shutil.copy2("README.html", dist_dir)
            print(f"  [OK] Copied README.html.")
            
        if os.path.exists("appearance_help.html"):
            shutil.copy2("appearance_help.html", dist_dir)
            print(f"  [OK] Copied appearance_help.html.")
        
        # Copy config.json template (for initial setup)
        if os.path.exists("config.json"):
            shutil.copy2("config.json", dist_dir)
            print(f"  [OK] Copied config.json.")
        
        # Copy license files
        if os.path.exists("LICENSE.md"):
            shutil.copy2("LICENSE.md", dist_dir)
            print(f"  [OK] Copied LICENSE.md.")
        
        if os.path.exists("THIRD_PARTY_LICENSES.md"):
            shutil.copy2("THIRD_PARTY_LICENSES.md", dist_dir)
            print(f"  [OK] Copied THIRD_PARTY_LICENSES.md.")
            
        print("\n" + "=" * 60)
        print("Ready for distribution!")
        print("=" * 60)
        print(f"\nDistribution folder: {os.path.abspath(dist_dir)}")
        print("\nNotes:")
        if tesseract_available:
            print("  1. Tesseract OCR is bundled (OCR function is available).")
            print("  2. Distribute all files in the dist folder.")
            print("  3. Double-click WuwaCalc.exe to start.")
        else:
            print("  1. Tesseract OCR is not bundled.")
            print("     To use the OCR function, Tesseract must be installed separately.")
            print("  2. Distribute all files in the dist folder.")
            print("  3. Double-click WuwaCalc.exe to start.")
        print("\n")
    else:
        print("\n" + "=" * 60)
        print("[ERROR] Build failed.")
        print("=" * 60)
        print("\nAn error occurred. Please check the messages above.")
        sys.exit(1)

if __name__ == "__main__":
    build()
