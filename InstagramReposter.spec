# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Get certifi's certificate bundle
import certifi
cert_path = certifi.where()
ssl_data = [(cert_path, 'cacert.pem')]  # Note the destination filename is fixed

# Define minimal needed data files
datas = [
    ('crypto.key', '.'),
    ('config.json', '.'),
    ('components/*.py', 'components'),
    ('utils/*.py', 'utils')
] + ssl_data  # Add SSL certificates

# Define what we need to include
a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'crypto_utils', 
        'instagrapi',
        'PIL._tkinter_finder',
        'customtkinter',
        'CTkMessagebox',
        'jaraco.text',
        'urllib3',
        # Video processing
        'moviepy',
        'moviepy.editor',
        'moviepy.video.io.VideoFileClip',
        'imageio',
        'proglog',
        'tqdm',
        'decorator',
        'imageio_ffmpeg',
        # SSL-related modules
        'ssl',
        '_ssl',
        'cryptography',
        'certifi',
        'requests',
        'requests.packages.urllib3.util.ssl_',
        'requests.packages.urllib3.contrib',
        'requests.adapters',
        'requests.sessions'
    ],
    hookspath=['hooks'],  # Add our hooks directory
    hooksconfig={},
    runtime_hooks=['hooks/ssl_hook.py'],  # Add our SSL runtime hook
    # Extensive list of excludes to reduce size
    excludes=[
        'matplotlib', 'pandas', 'scipy', 'sklearn', 'numpy', 'notebook', 
        'torch', 'torchvision', 'torchaudio', 'tensorflow', 'keras',
        'numba', 'cv2', 'kivy', 'pygments', 'lxml', 'jedi', 'parso',
        'IPython', 'sympy', 'pytest', 'sphinx', 'pydoc',
        'docutils', 'pytz', 'skimage', 'scikit-image',
        'fsspec', 'llvmlite', 'av', 'soundfile', 'openpyxl',
        'pycparser', 'pytest', 'pyarrow', 'h5py', 'transformers',
        'sqlalchemy', 'bokeh', 'scrapy', 'BeautifulSoup',
        'webview', 'playwright', 'yt_dlp', 'numexpr',
        'shapely', 'geopandas', 'tkinter.tix'
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Remove unwanted modules and binaries to reduce size further
def remove_prefix(modules, prefix):
    return [m for m in modules if not m.startswith(prefix)]

# Filter packages to keep SSL and cryptography-related modules
a.binaries = TOC([x for x in a.binaries if not (
    x[0].startswith(('scipy', 'sklearn', 'torch', 'tensorflow', 'pygame'))
)])
a.datas = TOC([x for x in a.datas if not x[0].startswith(('matplotlib', 'notebook', 'pandas'))])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='InstagramReposter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,  # Don't strip symbols to avoid SSL issues
    upx=True,
    upx_exclude=['libssl*.dll', 'libcrypto*.dll', '*_ssl*'],  # Don't compress SSL libraries
    runtime_tmpdir=None,
    console=False,  # Changed from True to False to remove the console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
