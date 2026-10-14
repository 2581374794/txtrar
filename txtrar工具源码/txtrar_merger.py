import io
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import zipfile
import zlib
from tkinter import filedialog

def _enable_dpi_awareness():
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

_enable_dpi_awareness()

rar_magic = b"Rar!\x1a\x07"
zip_magic = b"PK\x03\x04"
zip_span = b"PK\x07\x08"
seven_magic = b"7z\xbc\xaf\x27\x1c"
sep = b"\n\n-----RAR START-----\n"
tip = "合成文件结构：txt在前，rar在后；修改后缀为.rar即为压缩包，为.txt即为纯文本。"
output_tip = "合成后将输出.txtrar文件至本exe同目录的文件夹下；解压也将输出至此。"
unzip_tip = "除rar外也支持普通的zip/7z格式；分卷场景下被合成进 .txtrar的必须是第一分卷。"
txt_title = "选择txt文件"
rar_title = "选择rar文件"
txtrar_title = "选择txtrar文件"
txt_filter = [("txt文件", "*.txt"), ("所有文件", "*.*")]
rar_filter = [("rar文件", "*.rar"), ("所有文件", "*.*")]
txtrar_filter = [("txtrar文件", "*.txtrar"), ("所有文件", "*.*")]
bg = "#ffffff"
fg = "#222222"
fg_mute = "#666666"
fg_ok = "#0a6a2a"
border = "#c9ced6"
font = ("Microsoft YaHei UI", 9)
blue_light = dict(bg="#e8f1ff", fg="#17417a", hover="#d7e8ff", press="#c3dcff",
                  border="#9dc2f0")
blue_main = dict(bg="#2563eb", fg="#ffffff", hover="#1d4ed8", press="#1e40af",
                 border="#2563eb")
primary = dict(force_h=38, **blue_main)

class Error(Exception):
    pass

class RoundedButton(tk.Canvas):
    def __init__(self, master, text, command, bg="#f0f2f5", fg="#222222",
                 hover="#e4e7ec", press="#d8dce2", border="#d5d9df",
                 font=font, pad_x=28, pad_y=13, radius=9, force_h=None):
        f = tkfont.Font(font=font)
        self._bw = int(f.measure(text)) + int(pad_x)
        self._bh = int(force_h) if force_h else int(f.metrics("linespace")) + int(pad_y)
        self._text = text
        self._command = command
        self._bg = bg
        self._hover = hover
        self._press = press
        self._border = border
        self._fg = fg
        self._font = font
        self._radius = min(int(radius), self._bw // 2, self._bh // 2)
        super().__init__(master, width=self._bw, height=self._bh,
                         highlightthickness=0, bg=master.cget("bg"),
                         takefocus=0, cursor="hand2")
        self._paint(self._bg)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda e: self._paint(self._hover))
        self.bind("<Leave>", lambda e: self._paint(self._bg))

    def _round_points(self, x1, y1, x2, y2, r, steps=6):
        r = min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0)
        corners = ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0),
                   (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180))
        pts = []
        for cx, cy, a0 in corners:
            for i in range(steps + 1):
                a = math.radians(a0 + 90.0 * i / steps)
                pts.append(cx + r * math.cos(a))
                pts.append(cy + r * math.sin(a))
        return pts

    def _paint(self, color):
        self.delete("all")
        pts = self._round_points(1, 1, self._bw - 1, self._bh - 1, self._radius)
        self.create_polygon(pts, fill=color, outline="", smooth=True,
                            splinesteps=36)
        self.create_polygon(pts, fill="", outline=self._border, width=1,
                            smooth=True, splinesteps=36)
        self.create_text(self._bw / 2, self._bh / 2 - 0.75, text=self._text,
                         fill=self._fg, font=self._font)

    def _on_press(self, _):
        self._paint(self._press)

    def _on_release(self, _):
        self._paint(self._hover)
        if self._command:
            self._command()

def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

_engine_tried = []

def _engine_cache():
    return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "txtrar", "engine")

def _heal_engine():
    if not getattr(sys, "frozen", False):
        return None
    exe = os.path.abspath(sys.argv[0])
    try:
        with open(exe, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 88))
            cookie = f.read(88)
        magic, pkg, tocp, tocl, _, _ = struct.unpack("!8sIIii64s", cookie)
        if magic != b"MEI\014\013\012\013\016" or pkg > size:
            return None
        top = size - pkg
        with open(exe, "rb") as f:
            f.seek(top + tocp)
            toc = f.read(tocl)
        want = (b"UnRAR.exe", b"Rar.exe")
        got = {}
        i = 0
        while i + 18 <= len(toc):
            elen, pos, dlen, ulen, cflag, _ = struct.unpack("!iIIIBc", toc[i:i + 18])
            if elen <= 18 or i + elen > len(toc):
                break
            nm = toc[i + 18:i + elen].split(b"\x00")[0]
            if nm in want:
                with open(exe, "rb") as f:
                    f.seek(top + pos)
                    raw = f.read(dlen)
                if cflag:
                    raw = zlib.decompress(raw)
                if len(raw) == ulen:
                    got[nm] = raw
                if len(got) == len(want):
                    break
            i += elen
        if b"UnRAR.exe" not in got:
            return None
        work = _engine_cache()
        os.makedirs(work, exist_ok=True)
        for nm, raw in got.items():
            dst = os.path.join(work, nm.decode())
            tmp = dst + ".tmp"
            with open(tmp, "wb") as f:
                f.write(raw)
            os.replace(tmp, dst)
        return work
    except Exception:
        return None

def engine_dir():
    cands = []
    mei = getattr(sys, "_MEIPASS", None)
    if mei:
        cands.append(mei)
    here = os.path.dirname(os.path.abspath(sys.argv[0] if getattr(sys, "frozen", False) else __file__))
    cands.append(here)
    cands.append(os.path.join(here, "engine"))
    cands.append(_engine_cache())
    cands.append(r"C:\Program Files\WinRAR")
    for c in cands:
        if os.path.isfile(os.path.join(c, "UnRAR.exe")):
            return c
    work = _heal_engine()
    if work:
        return work
    _engine_tried[:] = cands
    return r"C:\Program Files\WinRAR"

def _rar_exe():
    exe = os.path.join(engine_dir(), "UnRAR.exe")
    if not os.path.isfile(exe):
        raise Error("解压引擎缺失：%s" % "、".join(_engine_tried))
    return exe

def _rar_tool():
    for c in (engine_dir(), r"C:\Program Files\WinRAR", r"C:\Program Files (x86)\WinRAR"):
        exe = os.path.join(c, "Rar.exe")
        if os.path.isfile(exe):
            return exe
    return None

def _hidden():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    return si

def find_sep(path):
    pos = 0
    tail = b""
    with open(path, "rb") as f:
        while True:
            chunk = f.read(4194304)
            if not chunk:
                return -1
            buf = tail + chunk
            i = buf.find(sep)
            if i >= 0:
                return pos - len(tail) + i + len(sep)
            tail = buf[-len(sep):]
            pos += len(chunk)

def payload_kind(head):
    if head.startswith(rar_magic):
        return "rar"
    if head.startswith(zip_magic) or head.startswith(zip_span):
        return "zip"
    if head.startswith(seven_magic):
        return "7z"
    return None

def volume_stem(name):
    prev = None
    while prev != name:
        prev = name
        name = re.sub(r"(?i)(\.part\d+|\.rar|\.zip|\.7z|\.z\d{2,3}|\.r\d{2,3}|\.\d{3})$", "", name)
    return name

def _peer_names(dirpath, stem, pattern):
    out = []
    low_stem = stem.lower()
    n = len(stem)
    try:
        names = os.listdir(dirpath)
    except OSError:
        return out
    for fn in names:
        low = fn.lower()
        if len(fn) > n and low.startswith(low_stem):
            if re.fullmatch(pattern, low[n:], re.I):
                out.append(fn)
    return out

def _vol_sort_key(fn, stem):
    suf = fn.lower()[len(stem):]
    m = re.fullmatch(r"\.z(\d{2,3})", suf)
    if m:
        return (0, int(m.group(1)), "")
    m = re.fullmatch(r"\.(\d{3})", suf)
    if m:
        return (0, int(m.group(1)), "")
    m = re.fullmatch(r"\.(?:zip|7z)\.(\d{3})", suf)
    if m:
        return (0, int(m.group(1)), "")
    return (1, 0, suf)

def _join_split_zip(vols, out_path):
    sizes = []
    for v in vols:
        try:
            sizes.append(os.path.getsize(v))
        except OSError:
            raise Error("分卷文件读取失败：%s" % v)
    bases = []
    acc = 0
    for s in sizes:
        bases.append(acc)
        acc += s
    with open(out_path, "wb") as out:
        for idx, v in enumerate(vols):
            with open(v, "rb") as f:
                first = True
                while True:
                    chunk = f.read(4194304)
                    if not chunk:
                        break
                    if first:
                        first = False
                        if idx == 0 and chunk[:4] == zip_span:
                            chunk = zip_magic + chunk[4:]
                    out.write(chunk)
    _fix_zip_offsets(out_path, bases)

def _fix_zip_offsets(path, bases):
    with open(path, "r+b") as f:
        f.seek(0, 2)
        size = f.tell()
        back = min(size, 65558)
        f.seek(size - back)
        tail = f.read(back)
        j = -1
        end = len(tail)
        while True:
            j = tail.rfind(b"PK\x05\x06", 0, end)
            if j < 0:
                raise Error("分卷zip结构异常：未找到压缩目录。")
            clen = struct.unpack_from("<H", tail, j + 20)[0]
            if j + 22 + clen == end:
                break
            end = j
        _sig, disk_no, cd_disk, _n1, _n2, cd_size, cd_off, _clen = struct.unpack_from(
            "<4sHHHHIIH", tail, j)
        if cd_disk >= len(bases):
            raise Error("分卷zip结构异常：目录所在分卷缺失。")
        new_cd = bases[cd_disk] + cd_off
        eocd_at = size - back + j
        f.seek(eocd_at + 4)
        f.write(struct.pack("<HH", 0, 0))
        f.seek(eocd_at + 16)
        f.write(struct.pack("<I", new_cd))
        if cd_size <= 0:
            return
        f.seek(new_cd)
        cd = f.read(cd_size)
        if len(cd) < cd_size:
            raise Error("分卷zip结构异常：压缩目录不完整。")
        pos = 0
        while pos + 46 <= len(cd) and cd[pos:pos + 4] == b"PK\x01\x02":
            (ndisk,) = struct.unpack_from("<H", cd, pos + 34)
            (loff,) = struct.unpack_from("<I", cd, pos + 42)
            if ndisk < len(bases):
                f.seek(new_cd + pos + 34)
                f.write(struct.pack("<H", 0))
                f.seek(new_cd + pos + 42)
                f.write(struct.pack("<I", bases[ndisk] + loff))
            nlen, xlen, clen2 = struct.unpack_from("<HHH", cd, pos + 28)
            pos += 46 + nlen + xlen + clen2

def _join_zip_volumes(work, stem, vols):
    if not vols:
        raise Error("分卷不完整：未找到zip分卷文件。")
    joined = os.path.join(work, stem + "._joined.zip")
    _join_split_zip(vols, joined)
    here = os.path.abspath(work)
    for v in vols:
        try:
            if os.path.dirname(os.path.abspath(v)) == here:
                os.remove(v)
        except OSError:
            pass
    return joined

def _same_file(a, b):
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            while True:
                x = fa.read(4194304)
                if x != fb.read(4194304):
                    return False
                if not x:
                    return True
    except OSError:
        return False

def _payload_equal_peer(p, off, peer):
    try:
        if os.path.getsize(p) - off != os.path.getsize(peer):
            return False
    except OSError:
        return False
    try:
        with open(p, "rb") as fp, open(peer, "rb") as fe:
            fp.seek(off)
            while True:
                cb = fe.read(4194304)
                if not cb:
                    return True
                pa = b""
                while len(pa) < len(cb):
                    chunk = fp.read(len(cb) - len(pa))
                    if not chunk:
                        return False
                    pa += chunk
                if pa != cb:
                    return False
    except OSError:
        return False

def _matches_any_peer(p, off, peers):
    try:
        psz = os.path.getsize(p) - off
    except OSError:
        return False
    for q in peers:
        try:
            if os.path.getsize(q) != psz:
                continue
        except OSError:
            continue
        if _payload_equal_peer(p, off, q):
            return True
    return False

_aes_id = 0x9901

def _aes_meta(info):
    e = info.extra or b""
    i = 0
    while i + 4 <= len(e):
        hid, sz = struct.unpack_from("<HH", e, i)
        if hid == _aes_id and sz >= 7 and i + 11 <= len(e):
            ver, _vendor, strength, method = struct.unpack_from("<HHBH", e, i + 4)
            return ver, strength, method
        i += 4 + sz
    return None

def _aes_saltkey(strength):
    if strength == 1:
        return 8, 16
    if strength == 2:
        return 12, 24
    if strength == 3:
        return 16, 32
    raise Error("该zip的AES加密强度不受支持。")

class _HmacSha1:
    def __init__(self, key):
        from Cryptodome.Hash import SHA1
        self._sha = SHA1
        if len(key) > 64:
            key = SHA1.new(key).digest()
        key = key + b"\x00" * (64 - len(key))
        self._opad = bytes(x ^ 0x5c for x in key)
        self._ipad = bytes(x ^ 0x36 for x in key)
        self._h = SHA1.new(self._ipad)

    def update(self, data):
        self._h.update(data)
        return self

    def digest(self):
        return self._sha.new(self._opad + self._h.digest()).digest()

    def reset(self):
        self._h = self._sha.new(self._ipad)
        return self

def _pbkdf2_sha1(pwd, salt, count, dklen):
    out = bytearray()
    block = 1
    while len(out) < dklen:
        h = _HmacSha1(pwd)
        u = h.update(salt + struct.pack(">I", block)).digest()
        t = bytearray(u)
        for _ in range(count - 1):
            u = h.reset().update(u).digest()
            for i in range(len(t)):
                t[i] ^= u[i]
        out += t
        block += 1
    return bytes(out[:dklen])

def _aes_ctr(key):
    from Cryptodome.Cipher import AES
    from Cryptodome.Util import Counter
    return AES.new(key, AES.MODE_CTR,
                   counter=Counter.new(128, little_endian=True))

def _cb7z(state):
    from py7zr.callbacks import ExtractCallback

    class _Cb(ExtractCallback):
        def report_start_preparation(self):
            pass

        def report_start(self, processing_file_path, processing_bytes):
            pass

        def report_update(self, decompressed_bytes):
            state["b"] += int(decompressed_bytes)

        def report_end(self, processing_file_path, wrote_bytes):
            pass

        def report_warning(self, message):
            pass

        def report_postprocess(self):
            pass

    return _Cb()

def _7z_error(e, soft):
    nm = type(e).__name__
    if nm == "UnsupportedCompressionMethodError":
        return Error("7z使用了本工具不支持的压缩算法，请改用 7-Zip / WinRAR 解压。")
    low = str(e).lower()
    if (any(k in low for k in ("password", "corrupt", "crc", "checksum",
                               "end of stream", "lzma"))
            or "crc" in nm.lower() or "lzma" in nm.lower()):
        return Error("解压密码不正确或文件已损坏。" if soft else "解压密码不正确。")
    return Error("7z解压失败：%s" % e)

def _aes_inflate(method, chunks):
    if method == 0:
        for c in chunks:
            yield c
        return
    if method == 8:
        d = zlib.decompressobj(-15)
    elif method == 12:
        import bz2
        d = bz2.BZ2Decompressor()
    elif method == 14:
        import lzma
        d = lzma.LZMADecompressor()
    else:
        raise Error("zip使用了不支持的压缩方式：%s" % method)
    for c in chunks:
        out = d.decompress(c)
        if out:
            yield out
    if method == 8:
        out = d.flush()
        if out:
            yield out

class _AesZip:
    def __init__(self, src, info, pwd, deep=True):
        meta = _aes_meta(info)
        if meta is None:
            raise Error("zip文件结构异常。")
        _ver, strength, method = meta
        salt_len, key_len = _aes_saltkey(strength)
        self._method = method
        self._f = open(src, "rb")
        try:
            self._f.seek(info.header_offset)
            hdr = self._f.read(30)
            if len(hdr) < 30 or hdr[:4] != zip_magic:
                raise Error("zip文件已损坏：本地文件头异常。")
            nlen, xlen = struct.unpack_from("<HH", hdr, 26)
            start = info.header_offset + 30 + nlen + xlen
            self._f.seek(start)
            salt = self._f.read(salt_len)
            pv = self._f.read(2)
            if len(salt) < salt_len or len(pv) < 2:
                raise Error("zip文件已损坏：加密头不完整。")
            self._size = info.compress_size - salt_len - 12
            if self._size < 0:
                raise Error("zip文件已损坏：加密数据长度异常。")
            dk = _pbkdf2_sha1(pwd.encode("utf-8"), salt, 1000, 2 * key_len + 2)
            if dk[2 * key_len:] != pv:
                raise Error("解压密码不正确。")
            if deep:
                mac = _HmacSha1(dk[key_len:2 * key_len])
                left = self._size
                while left > 0:
                    seg = self._f.read(min(1048576, left))
                    if not seg:
                        raise Error("zip文件已损坏：加密数据不完整。")
                    left -= len(seg)
                    mac.update(seg)
                if mac.digest()[:10] != self._f.read(10):
                    raise Error("解压密码不正确或文件已损坏。")
            self._f.seek(start + salt_len + 2)
            self._dec = _aes_ctr(dk[:key_len])
        except Exception:
            self._f.close()
            raise
        self._left = self._size

    def chunks(self):
        while self._left > 0:
            seg = self._f.read(min(1048576, self._left))
            if not seg:
                raise Error("zip文件已损坏：加密数据不完整。")
            self._left -= len(seg)
            yield self._dec.decrypt(seg)

    def plain(self):
        return _aes_inflate(self._method, self.chunks())

    def close(self):
        try:
            self._f.close()
        except OSError:
            pass

class _VolReader(io.RawIOBase):
    def __init__(self, vols):
        self._vols = list(vols)
        self._sizes = []
        for v in self._vols:
            try:
                self._sizes.append(os.path.getsize(v))
            except OSError:
                raise Error("分卷文件读取失败：%s" % v)
        self._bases = []
        acc = 0
        for s in self._sizes:
            self._bases.append(acc)
            acc += s
        self._total = acc
        self._pos = 0
        self._f = None
        self._fpos = -1
        self._cur = -1

    def readable(self):
        return True

    def seekable(self):
        return True

    def _vol_at(self, pos):
        i = len(self._bases) - 1
        while i > 0 and self._bases[i] > pos:
            i -= 1
        return i

    def _open(self, idx):
        if self._f is not None:
            try:
                self._f.close()
            except OSError:
                pass
        self._f = open(self._vols[idx], "rb")
        self._cur = idx
        self._fpos = -1

    def seek(self, off, whence=0):
        if whence == 1:
            self._pos += off
        elif whence == 2:
            self._pos = self._total + off
        else:
            self._pos = off
        if self._pos < 0:
            self._pos = 0
        return self._pos

    def tell(self):
        return self._pos

    def readinto(self, b):
        if self._pos >= self._total or not b:
            return 0
        idx = self._vol_at(self._pos)
        if self._f is None or self._cur != idx:
            self._open(idx)
        rel = self._pos - self._bases[idx]
        if rel != self._fpos:
            self._f.seek(rel)
            self._fpos = rel
        end = self._bases[idx + 1] if idx + 1 < len(self._vols) else self._total
        want = min(len(b), end - self._pos)
        n = self._f.readinto(memoryview(b)[:want])
        self._fpos += n
        self._pos += n
        return n

    def close(self):
        if self._f is not None:
            try:
                self._f.close()
            except OSError:
                pass
            self._f = None
        super().close()

def merge(txt_path, rar_path, progress=None):
    if not txt_path or not rar_path:
        raise Error("请先选择txt文件和rar文件。")
    for path, kind in ((txt_path, "txt"), (rar_path, "压缩")):
        if not os.path.isfile(path):
            raise Error("找不到%s文件：%s" % (kind, path))
    try:
        with open(rar_path, "rb") as f:
            head = f.read(8)
        if not payload_kind(head):
            base = os.path.basename(rar_path)
            mvol = re.search(r"(?i)\.(?:zip|7z)\.(\d{3})$", base)
            mz = re.search(r"(?i)\.z(\d{2,3})$", base)
            if (mvol and int(mvol.group(1)) > 1) or (mz and int(mz.group(1)) > 1):
                ext = "zip" if (mvol and base.lower().endswith(".zip." + mvol.group(1))) or mz else "7z"
                stem = volume_stem(base)
                suffix = ".zip.001" if ext == "zip" and mvol else (".z01" if ext == "zip" else ".7z.001")
                raise Error("检测到分卷%s：请使用第一分卷（%s%s）。" % (ext, stem, suffix))
            raise Error("这不是有效的压缩文件（rar/zip/7z）：%s" % rar_path)
    except Error:
        raise
    except OSError as e:
        raise Error("压缩文件读取失败：%s" % e)
    name_txt = os.path.splitext(os.path.basename(txt_path))[0]
    name_rar = os.path.splitext(os.path.basename(rar_path))[0]
    out_path = os.path.join(app_dir(), "%s+%s.txtrar" % (name_txt, name_rar))
    total = os.path.getsize(txt_path) + len(sep) + os.path.getsize(rar_path)
    done = 0
    try:
        with open(out_path, "wb") as out_f:
            for src in (txt_path, None, rar_path):
                if src is None:
                    out_f.write(sep)
                    done += len(sep)
                    if progress:
                        progress(done, total)
                    continue
                with open(src, "rb") as f:
                    while True:
                        chunk = f.read(4194304)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
    except OSError as e:
        raise Error("输出文件写入失败：%s" % e)
    return out_path

def auto_pick(paths):
    txt = ""
    rar = ""
    for p in paths:
        if not os.path.isfile(p):
            continue
        ext = os.path.splitext(p)[1].lower()
        if ext == ".txt" and not txt:
            txt = p
        elif ext == ".rar" and not rar:
            rar = p
        elif not txt:
            txt = p
        elif not rar:
            rar = p
    return txt, rar

def _outer_left(widget):
    try:
        import ctypes

        class R(ctypes.Structure):
            _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                        ("r", ctypes.c_long), ("b", ctypes.c_long)]
        hwnd = ctypes.windll.user32.GetParent(widget.winfo_id())
        r = R()
        if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return r.l
    except Exception:
        pass
    return widget.winfo_rootx()

def _present(win, parent):
    win.update_idletasks()
    win.geometry("%dx%d+%d+%d" % (parent.winfo_width(), win.winfo_reqheight(),
                                  parent.winfo_rootx(),
                                  parent.winfo_rooty() + parent.winfo_height() + 5))

    def place():
        if parent.winfo_ismapped() and win.winfo_ismapped():
            err = _outer_left(win) - _outer_left(parent)
            win.geometry("+%d+%d" % (win.winfo_x() - err,
                                     parent.winfo_rooty() +
                                     parent.winfo_height() + 5))

    for ms in (10, 40, 80, 160):
        win.after(ms, place)
    win.grab_set()
    win.lift()
    win.attributes("-topmost", True)
    win.after(300, lambda: win.attributes("-topmost", False))
    parent.wait_window(win)

def show_text(parent, text):
    win = tk.Toplevel(parent, bg=bg)
    win.title("txtrar的txt内容")
    win.transient(parent)
    win.resizable(False, False)
    t = tk.Text(win, font=font, fg=fg, bg=bg, wrap="word", bd=1,
                relief="solid", highlightthickness=1,
                highlightcolor="#2563eb", highlightbackground=border,
                width=72, height=16, padx=8, pady=6)
    t.pack(fill="both", expand=True, padx=14, pady=(14, 8))
    t.insert("1.0", text)
    t.config(state="disabled")
    _present(win, parent)

def _popup(parent, title, text, button=False):
    win = tk.Toplevel(parent, bg=bg)
    win.title(title)
    win.transient(parent)
    win.resizable(False, False)
    tk.Label(win, text=text, font=font, fg=fg, bg=bg, wraplength=0, anchor="w",
             justify="left").pack(anchor="w", padx=16,
                                  pady=(14, 4) if button else 14)
    if button:
        RoundedButton(win, "确定", win.destroy, **blue_main).pack(pady=(0, 12))
    win.bind("<Escape>", lambda _e: win.destroy())
    _present(win, parent)

def _bar(pct):
    pct = max(0.0, min(100.0, pct))
    filled = int(pct * 40 / 100)
    return "■" * filled + "□" * (40 - filled), pct

_cleanup_mutex = None

def _clean_orphans():
    try:
        tmp = tempfile.gettempdir()
        now = time.time()
        mine = getattr(sys, "_MEIPASS", "") or ""
        mine = os.path.realpath(mine) if mine else ""
        names = os.listdir(tmp)
    except Exception:
        return
    for name in names:
        p = os.path.join(tmp, name)
        try:
            if not os.path.isdir(p):
                continue
            if re.fullmatch(r"txtrar_[0-9a-z_]{8}", name):
                shutil.rmtree(p, ignore_errors=True)
                continue
            if name.startswith("_MEI"):
                if mine and os.path.realpath(p) == mine:
                    continue
                if now - os.stat(p).st_mtime < 3600:
                    continue
                if not os.path.isfile(os.path.join(p, "UnRAR.exe")):
                    continue
                if not os.path.isdir(os.path.join(p, "py7zr")):
                    continue
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            continue

def _startup_cleanup():
    global _cleanup_mutex
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.CreateMutexW.restype = wintypes.HANDLE
        k32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL,
                                     wintypes.LPCWSTR)
        k32.GetLastError.restype = wintypes.DWORD
        h = k32.CreateMutexW(None, False, "Local\\txtrar_tool_cleanup_v1")
        if not h:
            return
        if k32.GetLastError() == 183:
            return
        _cleanup_mutex = h
    except Exception:
        return
    threading.Thread(target=_clean_orphans, daemon=True).start()

class App(tk.Tk):
    def __init__(self, txt="", rar=""):
        super().__init__()
        self.title("txtrar工具")
        self.configure(bg=bg)
        self.resizable(True, False)
        self.txt_var = tk.StringVar(value=txt)
        self.rar_var = tk.StringVar(value=rar)
        self.txtrar_var = tk.StringVar(value="")
        self.pwd_var = tk.StringVar(value="")
        self.status = tk.StringVar(value=output_tip)
        self.info_var = tk.StringVar(value=unzip_tip)
        self.build_ui()
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        self.geometry("%dx%d+%d+%d" % (w, h, self.winfo_screenwidth() // 4,
                                       self.winfo_screenheight() // 4))
        self.minsize(w, 0)

    def build_ui(self):
        outer = tk.Frame(self, bg=bg)
        outer.pack(fill="x", padx=14, pady=(14, 0))
        rows = []

        def row(label, var, browse=None, extra=()):
            f = tk.Frame(outer, bg=bg)
            f.pack(fill="x", pady=(0, 8))
            lab = tk.Label(f, text=label, font=font, fg=fg, bg=bg,
                           anchor="w", padx=0)
            lab.grid(row=0, column=0, sticky="w")
            tk.Entry(f, textvariable=var, font=font, relief="solid", bd=1,
                     highlightthickness=1, highlightcolor="#2563eb",
                     highlightbackground=border).grid(
                row=0, column=1, sticky="ew", padx=(0, 8), ipady=4)
            col = 2
            if browse is not None:
                RoundedButton(f, "浏览", browse, **blue_light).grid(
                    row=0, column=col, sticky="e", padx=(0, 8 if extra else 0))
                col += 1
            for i, (t, c, style) in enumerate(extra):
                RoundedButton(f, t, c, **style).grid(
                    row=0, column=col, sticky="e",
                    padx=(0, 0 if i == len(extra) - 1 else 8))
                col += 1
            f.columnconfigure(1, weight=1)
            rows.append((f, lab))

        row("选txt文件：", self.txt_var, self.pick_txt)
        row("选rar文件：", self.rar_var, self.pick_rar)

        stat = tk.Frame(outer, bg=bg)
        stat.pack(fill="x", pady=(0, 8))
        tk.Label(stat, textvariable=self.status, font=font, fg=fg_ok, bg=bg,
                 anchor="w", justify="left", wraplength=0, padx=0,
                 pady=0).pack(side="left")
        RoundedButton(stat, "合成", self.do_merge, **primary).pack(side="right")

        row("txtrar文件：", self.txtrar_var, self.pick_txtrar)
        row("解压密码：", self.pwd_var,
            extra=(("查看", self.view_txt, primary),
                   ("解压", self.extract, primary)))

        tk.Label(outer, textvariable=self.info_var, font=font, fg=fg_ok, bg=bg,
                 anchor="w", justify="left", wraplength=0, padx=0,
                 pady=0).pack(fill="x", pady=(0, 8))

        self.update_idletasks()
        w = max(lab.winfo_reqwidth() for _, lab in rows)
        for f, lab in rows:
            f.columnconfigure(0, minsize=w)

        tk.Label(self, text=tip, font=font, fg=fg_mute, bg=bg, anchor="w",
                 justify="left", wraplength=0, padx=0, pady=0).pack(
            fill="x", padx=14, pady=(8, 10))

    def _pick(self, title, filetypes, var):
        p = filedialog.askopenfilename(title=title, initialdir=app_dir(),
                                       filetypes=filetypes)
        if p:
            var.set(p)
            self.status.set(output_tip)

    def pick_txt(self):
        self._pick(txt_title, txt_filter, self.txt_var)

    def pick_rar(self):
        self._pick(rar_title, rar_filter, self.rar_var)

    def pick_txtrar(self):
        self._pick(txtrar_title, txtrar_filter, self.txtrar_var)

    def info_bar(self, pct, label="已解压"):
        bar, pct = _bar(pct)
        self.info_var.set("%s： %s %.1f%%" % (label, bar, pct))
        self.update()

    def copy_payload(self, src_path, offset, dst):
        total = max(1, os.path.getsize(src_path) - offset)
        done = 0
        last = 0.0
        with open(src_path, "rb") as fi, open(dst, "wb") as fo:
            fi.seek(offset)
            while True:
                chunk = fi.read(4194304)
                if not chunk:
                    break
                fo.write(chunk)
                done += len(chunk)
                now = time.perf_counter()
                if now - last >= 0.03:
                    last = now
                    self.info_bar(done * 100.0 / total, "准备中")
        self.info_bar(100.0, "准备中")

    def check_password(self, path, off, work, pwd):
        probe = os.path.join(work, "_probe.rar")
        with open(path, "rb") as fi, open(probe, "wb") as fo:
            fi.seek(off)
            fo.write(fi.read(65536))
        r = subprocess.run(
            [_rar_exe(), "l", "-p" + pwd, probe], capture_output=True, cwd=work,
            startupinfo=_hidden(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if "密码" in (r.stdout + r.stderr).decode("gbk", "replace"):
            raise Error("解压密码不正确。")

    def check_zip(self, src, pwd):
        try:
            z = zipfile.ZipFile(src)
        except zipfile.BadZipFile as e:
            raise Error("zip文件已损坏或格式不支持：%s" % e)
        with z:
            infos = [i for i in z.infolist() if not i.is_dir()]
            if not infos:
                return
            enc = [i for i in infos if i.flag_bits & 0x1]
            if not enc:
                return
            if not pwd:
                raise Error("需要解压密码。")
            if _aes_meta(enc[0]) is not None:
                _AesZip(src, enc[0], pwd, False).close()
                return
            try:
                with z.open(enc[0], pwd=pwd.encode("utf-8")) as fi:
                    fi.read(1)
            except NotImplementedError as e:
                raise Error("zip使用了不支持的压缩方式：%s" % e)
            except RuntimeError as e:
                if "password" in str(e).lower():
                    raise Error("解压密码不正确。")
                raise Error("zip解压失败：%s" % e)
            except zipfile.BadZipFile as e:
                raise Error("zip文件已损坏：%s" % e)

    def check_7z(self, src, pwd, work):
        try:
            import py7zr
        except ImportError:
            raise Error("缺少7z解压组件。")
        try:
            z = py7zr.SevenZipFile(src, "r", password=pwd or None)
        except Exception as e:
            nm = type(e).__name__
            if nm == "PasswordRequired":
                raise Error("需要解压密码。")
            if nm == "LZMAError" or (pwd and nm == "CrcError"):
                raise Error("解压密码不正确。")
            raise Error("7z文件已损坏或格式不支持：%s" % e)
        try:
            if not z.needs_password():
                return
            if not pwd:
                raise Error("需要解压密码。")
            try:
                entries = z.list()
            except Exception as e:
                raise _7z_error(e, False)
            files = [f.filename for f in entries if not f.is_directory]
            if not files:
                return
            scratch = os.path.join(work, "_chk7z")
            shutil.rmtree(scratch, ignore_errors=True)
            os.makedirs(scratch, exist_ok=True)
            try:
                z.extract(path=scratch, targets=[files[0]], callback=_cb7z({"b": 0}))
            except Exception as e:
                raise _7z_error(e, False)
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
        finally:
            try:
                z.close()
            except Exception:
                pass

    def _run_unrar(self, src, outdir, pwd):
        args = [_rar_exe(), "x", "-o+", "-y", "-p" + pwd if pwd else "-p-",
                src, outdir + os.sep]
        proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, cwd=os.path.dirname(src),
            startupinfo=_hidden(),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        fd = proc.stdout.fileno()
        chunks = []
        tail = b""
        last = 0.0
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            chunks.append(chunk)
            tail = (tail + chunk)[-8192:]
            m = re.findall(rb"(\d+)%", tail)
            if m:
                now = time.perf_counter()
                if now - last >= 0.03:
                    last = now
                    self.info_bar(int(m[-1]))
        proc.wait()
        return proc.returncode, b"".join(chunks).decode("gbk", "replace")

    def repair_rar(self, src):
        rar = _rar_tool()
        if not rar:
            return False
        work = os.path.dirname(os.path.abspath(src))
        src_abs = os.path.abspath(src)
        targets = [src]
        for v in self._vol_paths(work, volume_stem(os.path.basename(src)),
                                 r"\.(?:part\d+\.rar|rar|r\d{2,3})"):
            if os.path.abspath(v) != src_abs:
                targets.append(v)
        self.info_var.set("检测到压缩包损坏，正在尝试用恢复记录修复…")
        self.update()
        done = False
        for t in targets:
            out = os.path.join(work, "fixed." + os.path.basename(t))
            try:
                if os.path.isfile(out):
                    os.remove(out)
            except OSError:
                pass
            try:
                subprocess.run([rar, "r", "-y", t], capture_output=True,
                               cwd=work, startupinfo=_hidden(),
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except OSError:
                continue
            if os.path.isfile(out) and not _same_file(out, t):
                os.replace(out, t)
                done = True
                break
        for fn in os.listdir(work):
            if fn.startswith("fixed.") or fn.startswith("rebuilt."):
                try:
                    os.remove(os.path.join(work, fn))
                except OSError:
                    pass
        return done

    def extract_rar(self, src, outdir, pwd, repair=False):
        rc, text = self._run_unrar(src, outdir, pwd)
        if rc != 0:
            if "密码" in text:
                raise Error("解压密码不正确。" if pwd else "需要解压密码。")
            if "分卷" in text or "下一" in text:
                raise Error("分卷不完整：请把其余分卷放在同一目录后重试。")
            if repair and self.repair_rar(src):
                rc, _ = self._run_unrar(src, outdir, pwd)
            if rc != 0:
                raise Error("解压失败（引擎返回码 %s）。" % rc)
        self.info_bar(100.0)

    def extract_zip(self, src, outdir, pwd):
        pwd_b = pwd.encode("utf-8") if pwd else None
        try:
            zf = zipfile.ZipFile(src)
        except zipfile.BadZipFile as e:
            raise Error("zip文件已损坏或格式不支持：%s" % e)
        with zf as z:
            infos = z.infolist()
            total = max(1, sum(i.file_size for i in infos))
            done = 0
            last = 0.0
            root = os.path.realpath(outdir)

            def emit(chunks, fo):
                nonlocal done, last
                for chunk in chunks:
                    fo.write(chunk)
                    done += len(chunk)
                    now = time.perf_counter()
                    if now - last >= 0.03:
                        last = now
                        self.info_bar(done * 100.0 / total)

            for info in infos:
                parts = [x for x in info.filename.replace("\\", "/").split("/")
                         if x not in ("", ".", "..")]
                if not parts:
                    continue
                target = os.path.realpath(os.path.join(root, *parts))
                if target != root and not target.startswith(root + os.sep):
                    raise Error("压缩包内含非法路径：%s" % info.filename)
                if info.is_dir():
                    os.makedirs(target, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(target), exist_ok=True)
                aes = _aes_meta(info) is not None
                if aes and not pwd:
                    raise Error("需要解压密码。")
                try:
                    if aes:
                        r = _AesZip(src, info, pwd)
                        try:
                            with open(target, "wb") as fo:
                                emit(r.plain(), fo)
                        finally:
                            r.close()
                    else:
                        with z.open(info, pwd=pwd_b) as fi, open(target, "wb") as fo:
                            emit(iter(lambda: fi.read(1048576), b""), fo)
                except Error:
                    raise
                except NotImplementedError as e:
                    raise Error("zip使用了不支持的压缩方式：%s" % e)
                except RuntimeError as e:
                    if "password" in str(e).lower():
                        raise Error("解压密码不正确。" if pwd else "需要解压密码。")
                    raise Error("zip解压失败：%s" % e)
                if info.date_time[0] >= 1980:
                    ts = time.mktime(info.date_time + (0, 0, -1))
                    os.utime(target, (ts, ts))
        self.info_bar(100.0)

    def extract_7z(self, src, outdir, pwd):
        try:
            import py7zr
        except ImportError:
            raise Error("缺少7z解压组件。")

        state = {"b": 0, "total": 1, "err": None, "done": False}

        def _work():
            try:
                with py7zr.SevenZipFile(src, "r", password=pwd or None) as z:
                    state["total"] = max(1, sum(f.uncompressed for f in z.list()
                                                if not f.is_directory))
                    z.extractall(path=outdir, callback=_cb7z(state))
            except Exception as e:
                state["err"] = e
            finally:
                state["done"] = True

        th = threading.Thread(target=_work, daemon=True)
        th.start()
        while not state["done"]:
            self.info_bar(state["b"] * 100.0 / state["total"])
            time.sleep(0.05)
        th.join()
        if state["err"] is not None:
            raise _7z_error(state["err"], True)
        self.info_bar(100.0)

    def _copy_peers(self, p, stem, work):
        base = os.path.basename(p)
        pat = r"\.(?:part\d+\.(?:rar|rev)|(?:zip|7z)\.\d{3}|rar|rev|r\d{2,3}|z\d{2,3}|zip|7z|\d{3})"
        dirs = dict.fromkeys((os.path.dirname(os.path.abspath(p)),
                              os.path.abspath(app_dir())))
        for d in dirs:
            for fn in _peer_names(d, stem, pat):
                if fn == base:
                    continue
                try:
                    shutil.copy2(os.path.join(d, fn), os.path.join(work, fn))
                except OSError:
                    pass

    def _vol_paths(self, work, stem, pattern):
        names = _peer_names(work, stem, pattern)
        names.sort(key=lambda fn: _vol_sort_key(fn, stem))
        return [os.path.join(work, x) for x in names]

    def _first_vol_name(self, work, stem):
        best = None
        for fn in _peer_names(work, stem, r"\.part\d+\.rar"):
            m = re.fullmatch(r"\.part(\d+)\.rar", fn[len(stem):], re.I)
            n = int(m.group(1))
            if best is None or n < best[0]:
                best = (n, m.group(1))
        if best is None:
            return stem + ".rar"
        return "%s.part%s.rar" % (stem, str(max(1, best[0] - 1)).zfill(len(best[1])))

    def _stage_001(self, work, stem, ext, p, off, packed):
        pat = r"\." + ext + r"\.\d{3}"
        vols = _peer_names(work, stem, pat)
        if not vols:
            return None
        vol1name = "%s.%s.001" % (stem, ext)
        if not packed and _matches_any_peer(
                p, 0, [os.path.join(work, x) for x in vols
                       if x.lower() != vol1name.lower()]):
            raise Error("此文件似乎是分卷%s的非首卷：请改用第一分卷（%s）。" % (ext, vol1name))
        vol1 = os.path.join(work, vol1name)
        if not os.path.isfile(vol1):
            self.copy_payload(p, off, vol1)
        elif not _payload_equal_peer(p, off, vol1):
            raise Error("检测到分卷%s：请将第一分卷（%s）与txt合成。" % (ext, vol1name))
        return self._vol_paths(work, stem, pat)

    def _stage(self, p, off, work, stem, kind, head):
        packed = bool(off)
        if kind == "rar":
            if not packed:
                return p, None
            self._copy_peers(p, stem, work)
            name = self._first_vol_name(work, stem)
            staged = os.path.join(work, name)
            if os.path.isfile(staged) and not _payload_equal_peer(p, off, staged):
                raise Error("此文件似乎是分卷rar的非首卷：请改用第一分卷（%s）。" % name)
            self.copy_payload(p, off, staged)
            return staged, None
        self._copy_peers(p, stem, work)
        if kind == "zip":
            if head[:4] == zip_span:
                if packed:
                    lead = os.path.join(work, stem + ".z01")
                    self.copy_payload(p, off, lead)
                else:
                    lead = p
                names = [x for x in _peer_names(work, stem, r"\.z\d{2,3}|\.zip")
                         if x.lower() != stem.lower() + ".z01"]
                names.sort(key=lambda fn: _vol_sort_key(fn, stem))
                return _join_zip_volumes(work, stem,
                                         [lead] + [os.path.join(work, x) for x in names]), None
            vols = self._stage_001(work, stem, "zip", p, off, packed)
            if vols is not None:
                return _join_zip_volumes(work, stem, vols), None
            if _peer_names(work, stem, r"\.z\d{2,3}"):
                raise Error("检测到分卷zip：请将第一分卷（%s.z01）与txt合成。" % stem)
            if not packed:
                return p, None
            staged = os.path.join(work, stem + ".zip")
            self.copy_payload(p, off, staged)
            return staged, None
        vols = self._stage_001(work, stem, "7z", p, off, packed)
        if vols is not None:
            return None, (lambda vv=vols: _VolReader(vv))
        if not packed:
            return p, None
        staged = os.path.join(work, stem + ".7z")
        self.copy_payload(p, off, staged)
        return staged, None

    def extract(self):
        if getattr(self, "extracting", False):
            return
        self.extracting = True
        reader = None
        try:
            p = self.txtrar_var.get().strip()
            if not p:
                raise Error("请先选择txtrar文件。")
            if not os.path.isfile(p):
                raise Error("找不到txtrar文件：%s" % p)
            pwd = self.pwd_var.get()
            base = os.path.splitext(os.path.basename(p))[0]
            outdir = os.path.join(app_dir(), base + "_解压")
            os.makedirs(outdir, exist_ok=True)
            work = tempfile.mkdtemp(prefix="txtrar_")
            try:
                with open(p, "rb") as f:
                    head = f.read(8)
                kind = payload_kind(head)
                off = 0
                if not kind:
                    off = find_sep(p)
                    if off < 0:
                        raise Error("无法识别的文件格式：%s" % p)
                    with open(p, "rb") as f:
                        f.seek(off)
                        head = f.read(8)
                    kind = payload_kind(head)
                    if not kind:
                        raise Error("未找到可解压的数据：%s" % p)
                name = base.rsplit("+", 1)[-1] if "+" in base else base
                stem = volume_stem(name)
                if kind == "rar" and pwd:
                    self.check_password(p, off, work, pwd)
                if off or kind != "rar":
                    src, factory = self._stage(p, off, work, stem, kind, head)
                else:
                    src, factory = p, None
                if kind == "zip":
                    self.check_zip(src, pwd)
                elif kind == "7z":
                    chk = factory() if factory else src
                    try:
                        self.check_7z(chk, pwd, work)
                    finally:
                        if factory:
                            chk.close()
                if kind == "7z" and factory:
                    reader = factory()
                    src = reader
                if kind == "rar":
                    self.extract_rar(src, outdir, pwd, src is not p)
                elif kind == "zip":
                    self.extract_zip(src, outdir, pwd)
                else:
                    self.extract_7z(src, outdir, pwd)
            finally:
                if reader is not None:
                    try:
                        reader.close()
                    except Exception:
                        pass
                shutil.rmtree(work, ignore_errors=True)
            _popup(self, "解压完成", "解压内容已输出至本exe同目录的文件夹下。")
        except Error as e:
            _popup(self, "出错了", str(e), True)
        except Exception as e:
            _popup(self, "出错了", "解压过程中发生错误：%s" % e, True)
        finally:
            self.extracting = False
            self.info_var.set(unzip_tip)

    def view_txt(self):
        p = self.txtrar_var.get().strip()
        if not p:
            _popup(self, "出错了", "请先选择txtrar文件。", True)
            return
        if not os.path.isfile(p):
            _popup(self, "出错了", "找不到txtrar文件：%s" % p, True)
            return
        try:
            with open(p, "rb") as f:
                data = f.read(262144)
        except OSError as e:
            _popup(self, "出错了", "文件读取失败：%s" % e, True)
            return
        i = data.find(sep)
        text = (data[:i] if i >= 0 else data).decode("utf-8", "replace")
        if len(text) > 20000:
            text = text[:20000]
        show_text(self, text)

    def show_progress(self, done, total):
        if total <= 0:
            return
        now = time.perf_counter()
        if now - getattr(self, "_last_ui", 0.0) < 0.03:
            return
        self._last_ui = now
        self.status.set(self.bar_text(done, total))
        self.update()

    def bar_text(self, done, total):
        bar, pct = _bar(done * 100.0 / total if total > 0 else 100.0)
        return "已合成： %s %.1f%%" % (bar, pct)

    def do_merge(self):
        if getattr(self, "merging", False):
            return
        self.merging = True
        try:
            merge(self.txt_var.get().strip(), self.rar_var.get().strip(),
                  self.show_progress)
            self.status.set(self.bar_text(1, 1))
            _popup(self, "合成完成", "合成内容已输出至本exe同目录的文件夹下。")
            self.status.set(output_tip)
        except Error as e:
            self.status.set(output_tip)
            _popup(self, "出错了", str(e), True)
        finally:
            self.merging = False

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    txt, rar = auto_pick(args)
    _startup_cleanup()
    app = App(txt, rar)
    if txt and rar:
        app.after(200, app.do_merge)
    app.mainloop()

if __name__ == "__main__":
    main()
