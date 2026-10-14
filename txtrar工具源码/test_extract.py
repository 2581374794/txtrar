import importlib.util
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import zipfile
import zlib

B5 = os.path.dirname(os.path.abspath(__file__))
TW = tempfile.mkdtemp(prefix="txtrar_regression_")
TMP = tempfile.gettempdir()
WINRAR_DIR = r"C:\Program Files\WinRAR"

shutil.copy2(os.path.join(B5, "txtrar_merger.py"), os.path.join(TW, "m.py"))

spec = importlib.util.spec_from_file_location("m", os.path.join(TW, "m.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["m"] = m
spec.loader.exec_module(m)

notes = []
dialogs = []
texts = []


def _popup(parent, title, text, button=False):
    (dialogs if button else notes).append((title, text))


m._popup = _popup
m.show_text = lambda parent, text: texts.append(text)

PASS = []
FAIL = []


def check(name, cond, info=""):
    if cond:
        PASS.append(name)
        print("PASS  %s" % name)
    else:
        FAIL.append((name, info))
        print("FAIL  %s  %s" % (name, info))


def crc32d(data):
    return zlib.crc32(data) & 0xFFFFFFFF


_CRCTAB = []


def _init_crctab():
    if not _CRCTAB:
        for n in range(256):
            c = n
            for _ in range(8):
                c = (c >> 1) ^ (0xEDB88320 if c & 1 else 0)
            _CRCTAB.append(c)


def crc1(ch, crc):
    return (crc >> 8) ^ _CRCTAB[(crc ^ ch) & 0xFF]


class ZipCrypt:
    def __init__(self, pwd):
        _init_crctab()
        self.k0, self.k1, self.k2 = 0x12345678, 0x23456789, 0x34567890
        for b in pwd:
            self.u(b)

    def u(self, b):
        self.k0 = crc1(b, self.k0)
        self.k1 = ((self.k1 + (self.k0 & 0xFF)) * 134775813 + 1) & 0xFFFFFFFF
        self.k2 = crc1(self.k1 >> 24, self.k2)

    def stream(self):
        t = (self.k2 | 2) & 0xFFFF
        return ((t * (t ^ 1)) >> 8) & 0xFF

    def enc(self, data):
        out = bytearray()
        for b in data:
            out.append(b ^ self.stream())
            self.u(b)
        return bytes(out)


def make_zipcrypto(path, entries, pwd):
    pwb = pwd.encode()
    out = bytearray()
    cd = bytearray()
    dword = ((2024 - 1980) << 9) | (1 << 5) | 1
    for name, data in entries:
        nb = name.encode()
        crc = crc32d(data)
        zc = ZipCrypt(pwb)
        hdr = bytes(range(0x30, 0x3B))
        enc_hdr = zc.enc(hdr + bytes([(crc >> 24) & 0xFF]))
        enc_data = zc.enc(data)
        off = len(out)
        out += struct.pack("<4sHHHHHIIIHH", b"PK\x03\x04", 20, 1, 0, 0, dword,
                           crc, len(enc_hdr) + len(data), len(data), len(nb), 0)
        out += nb
        out += enc_hdr + enc_data
        cd += struct.pack("<4sHHHHHHIIIHHHHHII", b"PK\x01\x02", 20, 20, 1, 0,
                          0, dword, crc, len(enc_hdr) + len(data), len(data),
                          len(nb), 0, 0, 0, 0, 0, off)
        cd += nb
    out += cd
    out += struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, 0, len(entries),
                       len(entries), len(cd), len(out) - len(cd), 0)
    with open(path, "wb") as f:
        f.write(bytes(out))


def make_aes_zip(path, entries, pwd, nbits=256):
    import pyzipper
    with pyzipper.AESZipFile(path, "w", compression=pyzipper.ZIP_DEFLATED,
                             encryption=pyzipper.WZ_AES,
                             encryption_kwargs={"nbits": nbits}) as z:
        z.setpassword(pwd.encode())
        for name, data in entries:
            z.writestr(name, data)


def make_plain_zip(path, entries):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(name, data)


def make_7z(path, entries, pwd=None):
    import py7zr
    tmpd = os.path.join(os.path.dirname(path), "_7zsrc")
    shutil.rmtree(tmpd, ignore_errors=True)
    os.makedirs(tmpd, exist_ok=True)
    for name, data in entries:
        with open(os.path.join(tmpd, name), "wb") as f:
            f.write(data)
    kw = dict(password=pwd) if pwd else {}
    with py7zr.SevenZipFile(path, "w", **kw) as z:
        for name in sorted(os.listdir(tmpd)):
            z.write(os.path.join(tmpd, name), arcname=name)
    shutil.rmtree(tmpd, ignore_errors=True)


def make_split_zip(zip_path, outdir, stem, nparts, span_marker=True):
    with open(zip_path, "rb") as f:
        data = f.read()
    size = len(data)
    i = data.rfind(b"PK\x05\x06")
    _sig, _dsk, _cdd, _n1, _n2, cd_size, cd_off, _cl = struct.unpack_from(
        "<4sHHHHIIH", data, i)
    cd = data[cd_off:cd_off + cd_size]
    entries = []
    pos = 0
    while pos + 46 <= len(cd) and cd[pos:pos + 4] == b"PK\x01\x02":
        nlen, xlen, clen2 = struct.unpack_from("<HHH", cd, pos + 28)
        entries.append(cd[pos:pos + 46 + nlen + xlen + clen2])
        pos += 46 + nlen + xlen + clen2
    part = size // nparts + 1
    bounds = [min(k * part, size) for k in range(nparts)]

    def vol_of(off):
        for k in range(nparts - 1):
            if bounds[k] <= off < bounds[k + 1]:
                return k
        return nparts - 1

    new_entries = []
    for e in entries:
        (loff,) = struct.unpack_from("<I", e, 42)
        d = vol_of(loff)
        ne = bytearray(e)
        struct.pack_into("<H", ne, 34, d)
        struct.pack_into("<I", ne, 42, loff - bounds[d])
        new_entries.append(bytes(ne))
    new_cd = b"".join(new_entries)
    last = nparts - 1
    last_body = data[bounds[last]:cd_off]
    last_vol = last_body + new_cd
    last_vol += struct.pack("<4sHHHHIIH", b"PK\x05\x06", 0, last, len(entries),
                            len(entries), len(new_cd), len(last_body), 0)
    vols = [data[bounds[k]:bounds[k + 1]] for k in range(nparts - 1)]
    vols.append(last_vol)
    if span_marker:
        vols[0] = b"PK\x07\x08" + vols[0][4:]
        exts = [".z%02d" % (k + 1) for k in range(nparts - 1)] + [".zip"]
    else:
        exts = [".zip.%03d" % (k + 1) for k in range(nparts)]
    for k, v in enumerate(vols):
        with open(os.path.join(outdir, stem + exts[k]), "wb") as f:
            f.write(v)
    return [stem + e for e in exts]


def make_split_zip7(src_zip, outdir, stem, nparts):
    return make_split_zip(src_zip, outdir, stem, nparts, span_marker=False)


def make_split_7z(src7z, outdir, stem, nparts):
    with open(src7z, "rb") as f:
        data = f.read()
    part = len(data) // nparts + 1
    names = []
    for k in range(nparts):
        seg = data[k * part:(k + 1) * part]
        nm = "%s.7z.%03d" % (stem, k + 1)
        with open(os.path.join(outdir, nm), "wb") as f:
            f.write(seg)
        names.append(nm)
    return names


def read_out(base):
    d = os.path.join(TW, base + "_解压")
    out = {}
    for root, dirs, files in os.walk(d):
        for fn in files:
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, d).replace("\\", "/")
            with open(p, "rb") as f:
                out[rel] = f.read()
    return out


def count_workdirs():
    try:
        return len([n for n in os.listdir(TMP)
                    if n.startswith("txtrar_") or n.startswith("_MEI")])
    except OSError:
        return -1


app = m.App()

ENTRIES = [
    ("f1.txt", b"hello world " * 40),
    ("f2.txt", b"second file content\n" * 30),
    ("big.bin", random.Random(7341).randbytes(400000)),
    ("after.bin", b"entry after multi-volume payload" * 31),
]

PHash = {n: crc32d(d) for n, d in ENTRIES}


def content_ok(got):
    if set(got.keys()) != {n for n, _ in ENTRIES}:
        return False
    return all(crc32d(got[n]) == PHash[n] for n in got)


def run_extract(path, pwd=""):
    notes.clear()
    dialogs.clear()
    app.txtrar_var.set(path)
    app.pwd_var.set(pwd)
    app.extract()
    return (dialogs[0][1] if dialogs else None), bool(notes)


txt_of = {}
for k in range(1, 40):
    p = os.path.join(TW, "T%d.txt" % k)
    with open(p, "w", encoding="utf-8") as f:
        f.write("第%d号文本内容\n" % k * 30)
    txt_of[k] = p

make_plain_zip(os.path.join(TW, "plain.zip"), ENTRIES)
make_zipcrypto(os.path.join(TW, "sec.zip"), ENTRIES, "pw123")
make_7z(os.path.join(TW, "plain.7z"), ENTRIES)
make_7z(os.path.join(TW, "sec.7z"), ENTRIES, pwd="pw123")

rar_fixture = None
rar_enc_fixture = None
try:
    if os.path.isfile(os.path.join(WINRAR_DIR, "WinRAR.exe")):
        rsrc = os.path.join(TW, "_rarsrc")
        os.makedirs(rsrc, exist_ok=True)
        for n, d in ENTRIES:
            with open(os.path.join(rsrc, n), "wb") as f:
                f.write(d)
        rar_fixture = os.path.join(TW, "A.rar")
        r = subprocess.run([os.path.join(WINRAR_DIR, "WinRAR.exe"), "a", "-ibck",
                            "-ep", "-y", rar_fixture] +
                           [os.path.join(rsrc, n) for n, _ in ENTRIES],
                           capture_output=True, timeout=120)
        if r.returncode != 0 or not os.path.isfile(rar_fixture):
            rar_fixture = None
        rar_enc_fixture = os.path.join(TW, "S.rar")
        r = subprocess.run([os.path.join(WINRAR_DIR, "WinRAR.exe"), "a", "-ibck",
                            "-ep", "-y", "-ppw123", rar_enc_fixture] +
                           [os.path.join(rsrc, n) for n, _ in ENTRIES],
                           capture_output=True, timeout=120)
        if r.returncode != 0 or not os.path.isfile(rar_enc_fixture):
            rar_enc_fixture = None
except Exception:
    rar_fixture = None
    rar_enc_fixture = None

SPLIT_NAMES = make_split_zip(os.path.join(TW, "plain.zip"), TW, "A", 4)
SPLIT7_NAMES = make_split_zip7(os.path.join(TW, "plain.zip"), TW, "B", 3)
S7Z_NAMES = make_split_7z(os.path.join(TW, "plain.7z"), TW, "C", 3)

base_work = count_workdirs()

outbase = [0]


def fresh_out(tag):
    outbase[0] += 1
    return "E%d" % outbase[0]


def do_flow(tag, txtrar_path, pwd=""):
    base = os.path.splitext(os.path.basename(txtrar_path))[0]
    shutil.rmtree(os.path.join(TW, base + "_解压"), ignore_errors=True)
    before = count_workdirs()
    err, ok = run_extract(txtrar_path, pwd)
    after = count_workdirs()
    return err, ok, before, after


t = "merged_plain_zip"
m.merge(txt_of[1], os.path.join(TW, "plain.zip"))
tp = os.path.join(TW, "T1+plain.txtrar")
check(t + "_exists", os.path.isfile(tp))
err, ok, b4, aft = do_flow(t, tp)
check(t, ok and err is None and content_ok(read_out("T1+plain")) and b4 == aft,
      "err=%s ok=%s work %s->%s" % (err, ok, b4, aft))

t = "merged_plain_7z"
m.merge(txt_of[2], os.path.join(TW, "plain.7z"))
tp = os.path.join(TW, "T2+plain.txtrar")
err, ok, b4, aft = do_flow(t, tp)
check(t, ok and err is None and content_ok(read_out("T2+plain")),
      "err=%s ok=%s" % (err, ok))

if rar_fixture:
    t = "merged_plain_rar"
    m.merge(txt_of[3], rar_fixture)
    tp = os.path.join(TW, "T3+A.txtrar")
    err, ok, b4, aft = do_flow(t, tp)
    check(t, ok and err is None and content_ok(read_out("T3+A")),
          "err=%s ok=%s" % (err, ok))

t = "zip_nopwd"
m.merge(txt_of[4], os.path.join(TW, "sec.zip"))
tp = os.path.join(TW, "T4+sec.txtrar")
err, ok, b4, aft = do_flow(t, tp)
check(t, (not ok) and err == "需要解压密码。", "err=%s" % err)

t = "zip_wrongpwd"
err, ok, b4, aft = do_flow(t, tp, "wrongpw")
check(t, (not ok) and err == "解压密码不正确。", "err=%s" % err)

t = "zip_rightpwd"
err, ok, b4, aft = do_flow(t, tp, "pw123")
check(t, ok and err is None and content_ok(read_out("T4+sec")),
      "err=%s ok=%s" % (err, ok))

for _nb in (128, 192, 256):
    _src = os.path.join(TW, "aes%d.zip" % _nb)
    make_aes_zip(_src, ENTRIES, "pw123", _nb)
    t = "zip_aes%d" % _nb
    m.merge(txt_of[5], _src)
    tp = os.path.join(TW, "T5+aes%d.txtrar" % _nb)
    err, ok, b4, aft = do_flow(t, tp, "pw123")
    check(t, ok and err is None and content_ok(read_out("T5+aes%d" % _nb)),
          "err=%s ok=%s" % (err, ok))

t = "zip_aes_nopwd"
err, ok, b4, aft = do_flow(t, tp)
check(t, (not ok) and err == "需要解压密码。", "err=%s" % err)

t = "zip_aes_wrongpwd"
err, ok, b4, aft = do_flow(t, tp, "wrongpw")
check(t, (not ok) and err == "解压密码不正确。", "err=%s" % err)

t = "7z_nopwd"
m.merge(txt_of[6], os.path.join(TW, "sec.7z"))
tp = os.path.join(TW, "T6+sec.txtrar")
err, ok, b4, aft = do_flow(t, tp)
check(t, (not ok) and err == "需要解压密码。", "err=%s" % err)

t = "7z_wrongpwd"
err, ok, b4, aft = do_flow(t, tp, "nope")
check(t, (not ok) and err == "解压密码不正确。", "err=%s" % err)

t = "7z_rightpwd"
err, ok, b4, aft = do_flow(t, tp, "pw123")
check(t, ok and err is None and content_ok(read_out("T6+sec")),
      "err=%s ok=%s" % (err, ok))

t = "splitzip_merged"
m.merge(txt_of[7], os.path.join(TW, SPLIT_NAMES[0]))
tp = os.path.join(TW, "T7+A.txtrar")
err, ok, b4, aft = do_flow(t, tp)
check(t, ok and err is None and content_ok(read_out("T7+A")),
      "err=%s ok=%s" % (err, ok))

t = "splitzip_unmerged"
unm = os.path.join(TW, "unm1")
shutil.rmtree(unm, ignore_errors=True)
os.makedirs(unm)
shutil.copy2(os.path.join(TW, SPLIT_NAMES[0]), os.path.join(unm, "A.txtrar"))
for nm in SPLIT_NAMES[1:]:
    shutil.copy2(os.path.join(TW, nm), os.path.join(unm, nm))
err, ok, b4, aft = do_flow(t, os.path.join(unm, "A.txtrar"))
check(t, ok and err is None and content_ok(read_out("A")),
      "err=%s ok=%s" % (err, ok))

t = "splitzip7_merged"
m.merge(txt_of[8], os.path.join(TW, SPLIT7_NAMES[0]))
tp = os.path.join(TW, "T8+B.zip.txtrar")
err, ok, b4, aft = do_flow(t, tp)
check(t, ok and err is None and content_ok(read_out("T8+B.zip")),
      "err=%s ok=%s" % (err, ok))

t = "splitzip7_wrongvol"
try:
    m.merge(txt_of[9], os.path.join(TW, SPLIT7_NAMES[1]))
    check(t, False, "非首卷未被拒绝")
except m.Error as e:
    check(t, "第一分卷" in str(e), "err=%s" % e)

t = "splitzip7_unmerged"
unm = os.path.join(TW, "unm2")
shutil.rmtree(unm, ignore_errors=True)
os.makedirs(unm)
shutil.copy2(os.path.join(TW, SPLIT7_NAMES[0]), os.path.join(unm, "B.zip.txrar"))
for nm in SPLIT7_NAMES[1:]:
    shutil.copy2(os.path.join(TW, nm), os.path.join(unm, nm))
err, ok, b4, aft = do_flow(t, os.path.join(unm, "B.zip.txrar"))
check(t, ok and err is None and content_ok(read_out("B.zip")),
      "err=%s ok=%s" % (err, ok))

t = "split7z_merged"
m.merge(txt_of[10], os.path.join(TW, S7Z_NAMES[0]))
tp = os.path.join(TW, "T10+C.7z.txtrar")
err, ok, b4, aft = do_flow(t, tp)
check(t, ok and err is None and content_ok(read_out("T10+C.7z")),
      "err=%s ok=%s" % (err, ok))

t = "split7z_wrongvol"
try:
    m.merge(txt_of[11], os.path.join(TW, S7Z_NAMES[1]))
    check(t, False, "非首卷未被拒绝")
except m.Error as e:
    check(t, "第一分卷" in str(e), "err=%s" % e)

t = "split7z_unmerged"
unm = os.path.join(TW, "unm3")
shutil.rmtree(unm, ignore_errors=True)
os.makedirs(unm)
shutil.copy2(os.path.join(TW, S7Z_NAMES[0]), os.path.join(unm, "C.7z.txrar"))
for nm in S7Z_NAMES[1:]:
    shutil.copy2(os.path.join(TW, nm), os.path.join(unm, nm))
err, ok, b4, aft = do_flow(t, os.path.join(unm, "C.7z.txrar"))
check(t, ok and err is None and content_ok(read_out("C.7z")),
      "err=%s ok=%s" % (err, ok))

t = "plain_zip_renamed"
shutil.copy2(os.path.join(TW, "plain.zip"), os.path.join(TW, "P.txrar"))
err, ok, b4, aft = do_flow(t, os.path.join(TW, "P.txrar"))
check(t, ok and err is None and content_ok(read_out("P")),
      "err=%s ok=%s" % (err, ok))

t = "plain_7z_renamed"
shutil.copy2(os.path.join(TW, "plain.7z"), os.path.join(TW, "Q.txrar"))
err, ok, b4, aft = do_flow(t, os.path.join(TW, "Q.txrar"))
check(t, ok and err is None and content_ok(read_out("Q")),
      "err=%s ok=%s" % (err, ok))

if rar_enc_fixture:
    t = "rar_enc_nopwd"
    m.merge(txt_of[12], rar_enc_fixture)
    tp = os.path.join(TW, "T12+S.txtrar")
    err, ok, b4, aft = do_flow(t, tp)
    check(t, (not ok) and "密码" in (err or ""), "err=%s" % err)

    t = "rar_enc_wrongpwd"
    err, ok, b4, aft = do_flow(t, tp, "badpw")
    check(t, (not ok) and err == "解压密码不正确。", "err=%s" % err)

    t = "rar_enc_rightpwd"
    err, ok, b4, aft = do_flow(t, tp, "pw123")
    check(t, ok and err is None and content_ok(read_out("T12+S")),
          "err=%s ok=%s" % (err, ok))

t = "bad_format"
bad = os.path.join(TW, "bad.txrar")
with open(bad, "wb") as f:
    f.write(b"this is not an archive at all " * 100)
err, ok, b4, aft = do_flow(t, bad)
check(t, (not ok) and err is not None and "无法识别" in err, "err=%s" % err)

t = "no_selection"
err, ok = run_extract("", "")
check(t, (not ok) and err == "请先选择txtrar文件。", "err=%s" % err)

t = "missing_file"
err, ok = run_extract(os.path.join(TW, "ghost.txtrar"), "")
check(t, (not ok) and err is not None and "找不到" in err, "err=%s" % err)

t = "view_txt"
texts.clear()
app.txtrar_var.set(os.path.join(TW, "T1+plain.txtrar"))
app.view_txt()
check(t, texts and texts[0].startswith("第1号文本内容"), "text=%r dialogs=%r" % (texts[:1], dialogs[-2:]))

t = "auto_pick"
a, b = m.auto_pick([os.path.join(TW, "T1.txt"), os.path.join(TW, "A.rar")])
check(t, os.path.basename(a) == "T1.txt" and os.path.basename(b) == "A.rar",
      "a=%s b=%s" % (a, b))

t = "merge_rejects_nonarchive"
try:
    m.merge(txt_of[1], os.path.join(TW, "bad.txrar"))
    check(t, False, "no error raised")
except m.Error as e:
    check(t, "不是有效的压缩文件" in str(e), "e=%s" % e)

t = "clean_orphans"
fake1 = os.path.join(TMP, "txtrar_aaaabbbb")
shutil.rmtree(fake1, ignore_errors=True)
os.makedirs(fake1)
with open(os.path.join(fake1, "x.bin"), "wb") as f:
    f.write(b"x")
keep1 = os.path.join(TMP, "txtrar_short")
shutil.rmtree(keep1, ignore_errors=True)
os.makedirs(keep1)
mei_old = os.path.join(TMP, "_MEIztestold")
shutil.rmtree(mei_old, ignore_errors=True)
os.makedirs(os.path.join(mei_old, "py7zr"))
with open(os.path.join(mei_old, "UnRAR.exe"), "wb") as f:
    f.write(b"MZ fake")
old_t = time.time() - 7200
os.utime(mei_old, (old_t, old_t))
mei_fresh = os.path.join(TMP, "_MEIztestfresh")
shutil.rmtree(mei_fresh, ignore_errors=True)
os.makedirs(os.path.join(mei_fresh, "py7zr"))
with open(os.path.join(mei_fresh, "UnRAR.exe"), "wb") as f:
    f.write(b"MZ fake")
mei_other = os.path.join(TMP, "_MEIztestother")
shutil.rmtree(mei_other, ignore_errors=True)
os.makedirs(mei_other)
with open(os.path.join(mei_other, "UnRAR.exe"), "wb") as f:
    f.write(b"MZ fake")
os.utime(mei_other, (old_t, old_t))
m._clean_orphans()
c1 = not os.path.isdir(fake1)
c2 = os.path.isdir(keep1)
c3 = not os.path.isdir(mei_old)
c4 = os.path.isdir(mei_fresh)
c5 = os.path.isdir(mei_other)
shutil.rmtree(keep1, ignore_errors=True)
shutil.rmtree(mei_fresh, ignore_errors=True)
shutil.rmtree(mei_other, ignore_errors=True)
check(t, c1 and c2 and c3 and c4 and c5,
      "fake_del=%s keep=%s meiold_del=%s meifresh=%s meiother=%s" % (c1, c2, c3, c4, c5))

t = "volume_stem_cases"
cases = {
    "A": "A", "A.part1": "A", "A.7z": "A", "A.7z.001": "A",
    "A.zip.001": "A", "A.z01": "A", "A.rar": "A",
}
okall = all(m.volume_stem(k) == v for k, v in cases.items())
check(t, okall, str({k: m.volume_stem(k) for k in cases}))

t = "payload_kind_span"
check(t, m.payload_kind(b"PK\x07\x08\x00\x00") == "zip"
      and m.payload_kind(b"PK\x03\x04") == "zip"
      and m.payload_kind(b"7z\xbc\xaf\x27\x1c") == "7z"
      and m.payload_kind(b"Rar!\x1a\x07") == "rar"
      and m.payload_kind(b"NOPE") is None)

try:
    app.destroy()
except Exception:
    pass

print("=" * 50)
print("PASS=%d FAIL=%d" % (len(PASS), len(FAIL)))
for name, info in FAIL:
    print("  FAILED: %s  %s" % (name, info))
shutil.rmtree(TW, ignore_errors=True)
sys.exit(1 if FAIL else 0)
