EXCLUDES = [
    'matplotlib', 'numpy', 'pandas', 'scipy', 'sympy', 'PIL', 'cv2',
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx', 'gi', 'gtk',
    'IPython', 'jupyter', 'notebook', 'nbformat', 'nbconvert', 'sphinx',
    'pytest', 'nose', 'unittest', 'test', 'pydoc', 'pydoc_data',
    'doctest', 'pdb', 'lib2to3', 'idlelib', 'curses', 'turtle', 'turtledemo',
    '_pyrepl',
    'setuptools', 'pkg_resources', '_distutils_hack', 'packaging',
    'pip', 'wheel', 'distutils',
    'ssl', '_ssl', '_hashlib',
    'psutil',
    'sqlite3', 'dbm', 'shelve', 'xmlrpc', 'ftplib', 'smtplib', 'imaplib',
    'poplib', 'nntplib', 'telnetlib', 'socketserver',
    'asyncio', 'concurrent', 'multiprocessing.dummy',
    'argparse', 'tarfile', 'unicodedata', 'statistics', 'decimal',
    '_pydecimal', 'fractions', 'numbers', 'gettext', 'pprint',
    'difflib', 'stringprep', 'encodings.idna',
    'mimetypes', 'gzip', 'tracemalloc',
    'html', 'xml', 'uuid',
    'wsgiref', 'mailbox', 'uu', 'binhex', 'cgi', 'cgitb', 'pty', 'tty',
    'termios', 'pipes', 'sndhdr', 'imghdr', 'chunk', 'colorsys', 'aifc',
    'sunau', 'wave', 'audioop', 'mailcap', 'netrc', 'rfc822',
    'symbol', 'tabnanny',
    'webbrowser', 'antigravity', 'this', 'zoneinfo', 'plistlib',
    'zipapp', 'compileall', 'py_compile', 'ensurepip', 'venv',
    'cProfile', 'profile', 'timeit', 'trace',
    'Cryptodome.PublicKey', 'Cryptodome.Signature', 'Cryptodome.Protocol',
    'Cryptodome.IO', 'Cryptodome.Math', 'Cryptodome.SelfTest',
    'Cryptodome.Util.strxor', 'Cryptodome.Util.asn1', 'Cryptodome.Util.RFC1751',
    'Cryptodome.Util.Padding',
    'Cryptodome.Cipher.ARC2', 'Cryptodome.Cipher.ARC4', 'Cryptodome.Cipher.Blowfish',
    'Cryptodome.Cipher.CAST', 'Cryptodome.Cipher.ChaCha20',
    'Cryptodome.Cipher.ChaCha20_Poly1305', 'Cryptodome.Cipher.DES',
    'Cryptodome.Cipher.DES3', 'Cryptodome.Cipher.PKCS1_OAEP',
    'Cryptodome.Cipher.PKCS1_v1_5', 'Cryptodome.Cipher.Salsa20',
    'Cryptodome.Cipher._EKSBlowfish', 'Cryptodome.Cipher._pkcs1_oaep_decode',
    'Cryptodome.Cipher._mode_cfb', 'Cryptodome.Cipher._mode_ofb',
    'Cryptodome.Cipher._mode_eax', 'Cryptodome.Cipher._mode_ccm',
    'Cryptodome.Cipher._mode_siv', 'Cryptodome.Cipher._mode_gcm',
    'Cryptodome.Cipher._mode_ocb', 'Cryptodome.Cipher._mode_kw',
    'Cryptodome.Cipher._mode_kwp', 'Cryptodome.Cipher._mode_openpgp',
    'Cryptodome.Hash.BLAKE2b', 'Cryptodome.Hash.BLAKE2s', 'Cryptodome.Hash.CMAC',
    'Cryptodome.Hash.KMAC128', 'Cryptodome.Hash.KMAC256',
    'Cryptodome.Hash.KangarooTwelve', 'Cryptodome.Hash.MD2',
    'Cryptodome.Hash.MD4', 'Cryptodome.Hash.MD5', 'Cryptodome.Hash.Poly1305',
    'Cryptodome.Hash.RIPEMD', 'Cryptodome.Hash.RIPEMD160', 'Cryptodome.Hash.SHA',
    'Cryptodome.Hash.SHA224', 'Cryptodome.Hash.SHA256', 'Cryptodome.Hash.SHA384',
    'Cryptodome.Hash.SHA512', 'Cryptodome.Hash.SHA3_224', 'Cryptodome.Hash.SHA3_256',
    'Cryptodome.Hash.SHA3_384', 'Cryptodome.Hash.SHA3_512',
    'Cryptodome.Hash.SHAKE128', 'Cryptodome.Hash.SHAKE256',
    'Cryptodome.Hash.TupleHash128', 'Cryptodome.Hash.TupleHash256',
    'Cryptodome.Hash.TurboSHAKE128', 'Cryptodome.Hash.TurboSHAKE256',
    'Cryptodome.Hash.cSHAKE128', 'Cryptodome.Hash.cSHAKE256',
    'Cryptodome.Hash.keccak',
    'csv', 'http', 'brotli',
    'multiprocessing.managers', 'multiprocessing.pool',
    'multiprocessing.shared_memory',
]

KEEP_BIN = (
    '_raw_aes.pyd', '_raw_aesni.pyd', '_raw_cbc.pyd', '_raw_ctr.pyd',
    '_SHA1.pyd', '_cpuid_c.pyd',
)

DROP_BIN = ('unicodedata.pyd', '_decimal.pyd', '_wmi.pyd')

DROP_BIN_PREFIX = ('_brotli',)


def _base(name):
    return name.replace('/', '\\').rsplit('\\', 1)[-1]


def _tk_icon():
    import os as _os
    import shutil as _sh
    import sys as _sys
    import tempfile as _tf
    for base in (getattr(_sys, "base_prefix", ""), getattr(_sys, "prefix", "")):
        if not base:
            continue
        for sub in ("DLLs", ""):
            p = _os.path.join(base, sub, "tcl9tk90.dll")
            if _os.path.isfile(p):
                d = _tf.mkdtemp(prefix="tkicon_")
                q = _os.path.join(d, "tkicon.exe")
                _sh.copy2(p, q)
                return q + ",0"
    return None


a = Analysis(
    ['txtrar_merger.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('engine/UnRAR.exe', '.'),
        ('engine/Rar.exe', '.'),
    ],
    hiddenimports=[
        'py7zr', 'py7zr.callbacks', 'zlib', 'struct',
        'Cryptodome.Cipher.AES', 'Cryptodome.Cipher._mode_ctr',
        'Cryptodome.Util.Counter', 'Cryptodome.Hash.SHA1',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,
)

a.binaries = [b for b in a.binaries
              if _base(b[0]) not in DROP_BIN
              and not _base(b[0]).startswith(DROP_BIN_PREFIX)
              and ('Cryptodome' not in b[0] or _base(b[0]) in KEEP_BIN)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='txtrar工具',
    icon=_tk_icon(),
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
