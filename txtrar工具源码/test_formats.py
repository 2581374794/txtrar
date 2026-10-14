import importlib.util
import os
import random
import shutil
import subprocess
import sys
import tempfile
import zipfile
import zlib

B5 = os.path.dirname(os.path.abspath(__file__))
TW = tempfile.mkdtemp(prefix="txtrar_formats_")
SRCD = os.path.join(TW, "_src")

shutil.copy2(os.path.join(B5, "txtrar_merger.py"), os.path.join(TW, "m.py"))
spec = importlib.util.spec_from_file_location("m", os.path.join(TW, "m.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["m"] = m
spec.loader.exec_module(m)

m._popup = lambda parent, title, text, button=False: (
    dialogs if button else notes).append((title, text))
m.show_text = lambda parent, text: None

try:
    import pyzipper
except ImportError:
    pyzipper = None

try:
    import py7zr
except ImportError:
    py7zr = None


def find_tool(names, dirs):
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    for d in dirs:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
    return None


RAR = find_tool(["Rar.exe"], [r"C:\Program Files\WinRAR", r"C:\Program Files (x86)\WinRAR"])
WINRAR = find_tool(["WinRAR.exe"], [r"C:\Program Files\WinRAR", r"C:\Program Files (x86)\WinRAR"])
SZ = find_tool(["7za.exe", "7z.exe"], [r"C:\Program Files\7-Zip", B5, os.getcwd()])

print("Rar.exe     = %s" % RAR)
print("WinRAR.exe  = %s" % WINRAR)
print("7za/7z      = %s" % SZ)
print("pyzipper    = %s" % (pyzipper.__name__ if pyzipper else "缺失（AES 用例将跳过）"))
print()

PASS = []
FAIL = []
SKIP = []


def check(name, cond, info=""):
    (PASS if cond else FAIL).append(name if cond else (name, info))
    print(("PASS  " if cond else "FAIL  ") + name + ("" if cond else "  " + str(info)))


def skip(name):
    SKIP.append(name)
    print("SKIP  " + name)


def crc32d(data):
    return zlib.crc32(data) & 0xFFFFFFFF


ENTRIES = [
    ("f1.txt", b"hello world " * 40),
    ("f2.txt", b"second file content\n" * 30),
    ("big.bin", random.Random(7341).randbytes(400000)),
    ("after.bin", b"entry after multi-volume payload " * 31),
]
PHash = {n: crc32d(d) for n, d in ENTRIES}


def make_src():
    shutil.rmtree(SRCD, ignore_errors=True)
    os.makedirs(SRCD)
    for n, d in ENTRIES:
        with open(os.path.join(SRCD, n), "wb") as f:
            f.write(d)


def clean_prefix(stem):
    for fn in os.listdir(TW):
        if fn.startswith(stem + "."):
            try:
                os.remove(os.path.join(TW, fn))
            except OSError:
                pass


def build(tool, args, stem, ext, first):
    clean_prefix(stem)
    tgt = os.path.join(TW, stem + ext)
    r = subprocess.run([tool] + list(args) + [tgt] + [n for n, _ in ENTRIES],
                       cwd=SRCD, capture_output=True, timeout=300)
    if r.returncode != 0 or not os.path.isfile(os.path.join(TW, first)):
        return None
    return os.path.join(TW, first)


def rar(stem, extra=()):
    first = stem + (".part1.rar" if "-v" in " ".join(extra) else ".rar")
    if "-v" not in " ".join(extra):
        return build(RAR, ["a", "-ibck", "-ep", "-y"] + list(extra), stem, ".rar", first)
    clean_prefix(stem)
    r = subprocess.run([RAR, "a", "-ibck", "-ep", "-y"] + list(extra) +
                       [os.path.join(TW, stem + ".rar")] + [n for n, _ in ENTRIES],
                       cwd=SRCD, capture_output=True, timeout=300)
    vols = sorted((f for f in os.listdir(TW) if f.startswith(stem + ".part")),
                  key=lambda f: int(f.rsplit(".", 2)[-2][4:]))
    return os.path.join(TW, vols[0]) if r.returncode == 0 and vols else None


def zipw(stem, extra=()):
    first = stem + (".z01" if "-v" in " ".join(extra) else ".zip")
    return build(WINRAR, ["a", "-ibck", "-ep", "-y", "-afzip"] + list(extra),
                 stem, ".zip", first)


def zip7(stem, extra=()):
    first = stem + (".zip.001" if "-v" in " ".join(extra) else ".zip")
    return build(SZ, ["a", "-tzip", "-y", "-bso0", "-bsp0"] + list(extra),
                 stem, ".zip", first)


def z7(stem, extra=()):
    first = stem + (".7z.001" if "-v" in " ".join(extra) else ".7z")
    return build(SZ, ["a", "-t7z", "-y", "-bso0", "-bsp0"] + list(extra),
                 stem, ".7z", first)


def zipfile_make(stem, mode):
    clean_prefix(stem)
    tgt = os.path.join(TW, stem + ".zip")
    with zipfile.ZipFile(tgt, "w", mode) as z:
        for n, d in ENTRIES:
            z.writestr(zipfile.ZipInfo(n, (2024, 1, 1, 0, 0, 0)), d)
    return tgt


def aes_zip(stem, nbits):
    clean_prefix(stem)
    tgt = os.path.join(TW, stem + ".zip")
    with pyzipper.AESZipFile(tgt, "w", compression=pyzipper.ZIP_DEFLATED,
                             encryption=pyzipper.WZ_AES,
                             encryption_kwargs={"nbits": nbits}) as z:
        z.setpassword(b"pw123")
        for n, d in ENTRIES:
            z.writestr(n, d)
    return tgt


def read_out(base):
    d = os.path.join(TW, base + "_解压")
    out = {}
    for root, _dirs, files in os.walk(d):
        for fn in files:
            p = os.path.join(root, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, d).replace("\\", "/")] = f.read()
    return out


def content_ok(got):
    if set(got.keys()) != {n for n, _ in ENTRIES}:
        return False
    return all(crc32d(got[n]) == PHash[n] for n in got)


TXTS = {}


def txt_for(k):
    p = os.path.join(TW, "T%d.txt" % k)
    with open(p, "w", encoding="utf-8") as f:
        f.write("第%d号文本内容\n" % k * 30)
    return p


def run(tag, arc, pwd="", expect="ok"):
    if not arc:
        skip(tag)
        return
    TXTS[tag] = txt_for(len(TXTS) + 1)
    try:
        tp = m.merge(TXTS[tag], arc)
    except m.Error as e:
        check(tag, False, "merge raised: %s" % e)
        return
    base = os.path.splitext(os.path.basename(tp))[0]
    shutil.rmtree(os.path.join(TW, base + "_解压"), ignore_errors=True)
    notes.clear()
    dialogs.clear()
    app.txtrar_var.set(tp)
    app.pwd_var.set(pwd)
    app.extract()
    err = dialogs[0][1] if dialogs else None
    if expect == "ok":
        got = read_out(base)
        check(tag, not err and content_ok(got), "err=%s files=%s" % (err, sorted(got)))
    elif expect == "nopwd":
        check(tag, err == "需要解压密码。", "err=%s" % err)
    elif expect == "badpwd":
        check(tag, err == "解压密码不正确。", "err=%s" % err)
    shutil.rmtree(os.path.join(TW, base + "_解压"), ignore_errors=True)
    try:
        os.remove(tp)
    except OSError:
        pass


notes = []
dialogs = []
make_src()
app = m.App()

print("== rar ==")
if RAR:
    run("rar5_normal", rar("R1"))
    run("rar4", rar("R2", ["-ma4"]))
    run("rar5_store_m0", rar("R3", ["-m0"]))
    run("rar5_best_m5", rar("R4", ["-m5"]))
    run("rar5_solid", rar("R5", ["-s"]))
    run("rar4_solid", rar("R6", ["-ma4", "-s"]))
    run("rar5_rr5p", rar("R7", ["-rr5p"]))
    run("rar5_pwd_nopwd", rar("R8", ["-ppw123"]), "", "nopwd")
    run("rar5_pwd_wrong", rar("R8", ["-ppw123"]), "nope", "badpwd")
    run("rar5_pwd_ok", rar("R8", ["-ppw123"]), "pw123", "ok")
    run("rar4_pwd_ok", rar("R9", ["-ma4", "-ppw123"]), "pw123", "ok")
    run("rar5_solid_pwd", rar("R10", ["-s", "-ppw123"]), "pw123", "ok")
    run("rar5_hp_ok", rar("R11", ["-hppw123"]), "pw123", "ok")
    run("rar5_hp_wrong", rar("R11", ["-hppw123"]), "nope", "badpwd")
    run("rar5_hp_nopwd", rar("R11", ["-hppw123"]), "", "nopwd")
    run("rar5_split", rar("R12", ["-v100k"]))
    run("rar5_split_pwd", rar("R13", ["-v100k", "-ppw123"]), "pw123", "ok")
    run("rar4_split", rar("R14", ["-ma4", "-v100k"]))
    run("rar5_split_solid", rar("R15", ["-v100k", "-s"]))
    run("rar5_split_10vol", rar("R16", ["-v20k"]))
else:
    for t in ("rar5_normal", "rar4", "rar5_store_m0", "rar5_best_m5", "rar5_solid",
              "rar4_solid", "rar5_rr5p", "rar5_pwd_nopwd", "rar5_pwd_wrong",
              "rar5_pwd_ok", "rar4_pwd_ok", "rar5_solid_pwd", "rar5_hp_ok",
              "rar5_hp_wrong", "rar5_hp_nopwd", "rar5_split", "rar5_split_pwd",
              "rar4_split", "rar5_split_solid", "rar5_split_10vol"):
        skip(t)

print("== zip ==")
run("zip_deflate", zipw("Z1") if WINRAR else None)
run("zip_store", zipw("Z2", ["-m0"]) if WINRAR else None)
run("zip_bzip2", zipfile_make("Z3", zipfile.ZIP_BZIP2))
run("zip_lzma", zipfile_make("Z4", zipfile.ZIP_LZMA))
run("zip_stored", zipfile_make("Z5", zipfile.ZIP_STORED))
run("zip_zipcrypto_ok", zipw("Z7", ["-ppw123"]) if WINRAR else None, "pw123", "ok")
run("zip_zipcrypto_nopwd", zipw("Z7", ["-ppw123"]) if WINRAR else None, "", "nopwd")
run("zip_zipcrypto_wrong", zipw("Z7", ["-ppw123"]) if WINRAR else None, "nope", "badpwd")
run("zip_zipcrypto_7z_ok", zip7("Z13", ["-ppw123", "-mem=ZipCrypto"]) if SZ else None, "pw123", "ok")
for _nb in (128, 192, 256):
    run("zip_aes%d" % _nb, aes_zip("ZA%d" % _nb, _nb) if pyzipper else None, "pw123", "ok")
run("zip_aes_nopwd", aes_zip("ZA256", 256) if pyzipper else None, "", "nopwd")
run("zip_aes_wrong", aes_zip("ZA256", 256) if pyzipper else None, "nope", "badpwd")
run("zip_aes256_from_7zip", zip7("Z16", ["-ppw123", "-mem=AES256"]) if SZ else None, "pw123", "ok")
run("zip_split_z01", zipw("Z11", ["-v100k"]) if WINRAR else None)
run("zip_split_z01_pwd", zipw("Z12", ["-v100k", "-ppw123"]) if WINRAR else None, "pw123", "ok")
run("zip_split_001", zip7("Z14", ["-v100k"]) if SZ else None)
run("zip_split_001_pwd", zip7("Z15", ["-v100k", "-ppw123", "-mem=ZipCrypto"]) if SZ else None, "pw123", "ok")

print("== 7z ==")
run("7z_lzma2", z7("S1") if SZ else None)
run("7z_lzma", z7("S2", ["-m0=LZMA"]) if SZ else None)
run("7z_bzip2", z7("S3", ["-m0=BZip2"]) if SZ else None)
run("7z_deflate", z7("S4", ["-m0=Deflate"]) if SZ else None)
run("7z_copy", z7("S5", ["-m0=Copy"]) if SZ else None)
run("7z_delta_lzma2", z7("S6", ["-m0=Delta:4", "-m1=LZMA2"]) if SZ else None)
run("7z_bcj_lzma2", z7("S7", ["-m0=BCJ", "-m1=LZMA2"]) if SZ else None)
run("7z_ppmd", z7("S8", ["-m0=PPMd"]) if SZ else None)
run("7z_arm", z7("S13", ["-m0=ARM", "-m1=LZMA2"]) if SZ else None)
run("7z_pwd_ok", z7("S9", ["-ppw123", "-mhe=off"]) if SZ else None, "pw123", "ok")
run("7z_pwd_nopwd", z7("S9", ["-ppw123", "-mhe=off"]) if SZ else None, "", "nopwd")
run("7z_pwd_wrong", z7("S9", ["-ppw123", "-mhe=off"]) if SZ else None, "nope", "badpwd")
run("7z_he_ok", z7("S10", ["-ppw123", "-mhe=on"]) if SZ else None, "pw123", "ok")
run("7z_he_nopwd", z7("S10", ["-ppw123", "-mhe=on"]) if SZ else None, "", "nopwd")
run("7z_he_wrong", z7("S10", ["-ppw123", "-mhe=on"]) if SZ else None, "nope", "badpwd")
run("7z_split", z7("S11", ["-v100k"]) if SZ else None)
run("7z_split_pwd", z7("S12", ["-v100k", "-ppw123", "-mhe=on"]) if SZ else None, "pw123", "ok")


def py7zr_make(stem, fid):
    if py7zr is None:
        return None
    clean_prefix(stem)
    tgt = os.path.join(TW, stem + ".7z")
    with py7zr.SevenZipFile(tgt, "w", filters=[{"id": fid}]) as z:
        for n, _ in ENTRIES:
            z.write(os.path.join(SRCD, n), n)
    return tgt


run("7z_zstd", py7zr_make("S14", py7zr.FILTER_ZSTD) if py7zr else None)

print("== 边界：不支持的算法应明确报错 ==")


def expect_err(tag, arc, needle, pwd=""):
    if not arc:
        skip(tag)
        return
    TXTS[tag] = txt_for(len(TXTS) + 1)
    tp = m.merge(TXTS[tag], arc)
    base = os.path.splitext(os.path.basename(tp))[0]
    dialogs.clear()
    app.txtrar_var.set(tp)
    app.pwd_var.set(pwd)
    app.extract()
    err = dialogs[0][1] if dialogs else None
    check(tag, bool(err) and needle in err, "err=%s" % err)
    try:
        os.remove(tp)
    except OSError:
        pass
    shutil.rmtree(os.path.join(TW, base + "_解压"), ignore_errors=True)


if SZ:
    expect_err("zip_deflate64", zip7("B1", ["-mm=Deflate64"]), "不支持的压缩方式")
    expect_err("zip_ppmd", zip7("B2", ["-mm=PPMd"]), "不支持的压缩方式")
    expect_err("7z_bcj2", z7("B3", ["-m0=BCJ2", "-m1=LZMA2"]), "不支持的压缩算法")
    expect_err("7z_arm64", z7("B4", ["-m0=ARM64", "-m1=LZMA2"]), "不支持的压缩算法")
else:
    for t in ("zip_deflate64", "zip_ppmd", "7z_bcj2", "7z_arm64"):
        skip(t)

if py7zr is None:
    skip("7z_brotli_unsupported")
else:
    _barc = py7zr_make("S15", py7zr.FILTER_BROTLI)
    import py7zr.compressor as _p7c
    _saved_brotli = _p7c.brotli
    _p7c.brotli = None
    try:
        expect_err("7z_brotli_unsupported", _barc, "不支持的压缩算法")
    finally:
        _p7c.brotli = _saved_brotli

print("== 非 ASCII 文件名 ==")
UNI = [("中文 文件.txt", b"chinese name " * 50),
       ("日本語データ.bin", random.Random(99).randbytes(120000))]
ENTRIES[:] = UNI
PHash.clear()
PHash.update({n: crc32d(d) for n, d in UNI})
make_src()
run("zip_unicode_names", zip7("U1") if SZ else None)
run("7z_unicode_names", z7("U2") if SZ else None)
run("rar_unicode_names", rar("U3") if RAR else None)

print("== 恢复记录(-rr) / 恢复卷(.rev) ==")
RRARC = rar("R1", ["-m0", "-rr5p"]) if RAR else None


def flow(tag, tp, pwd=""):
    base = os.path.splitext(os.path.basename(tp))[0]
    shutil.rmtree(os.path.join(TW, base + "_解压"), ignore_errors=True)
    notes.clear()
    dialogs.clear()
    app.txtrar_var.set(tp)
    app.pwd_var.set(pwd)
    app.extract()
    err = dialogs[0][1] if dialogs else None
    got = read_out(base)
    shutil.rmtree(os.path.join(TW, base + "_解压"), ignore_errors=True)
    return err, got


def break_payload(path, nbytes=200):
    off = m.find_sep(path)
    b = bytearray(open(path, "rb").read())
    k = off + (len(b) - off) // 2
    for i in range(k, min(k + nbytes, len(b))):
        b[i] ^= 0xFF
    open(path, "wb").write(b)


def break_file(path, nbytes):
    b = bytearray(open(path, "rb").read())
    k = len(b) // 2
    for i in range(k, min(k + nbytes, len(b))):
        b[i] ^= 0xFF
    open(path, "wb").write(b)


if not RRARC:
    for t in ("rr_repair", "rr_no_record_fails", "rr_repair_multivol", "rev_restore_missing"):
        skip(t)
else:
    tp = m.merge(txt_for(90), RRARC)
    os.remove(RRARC)
    break_payload(tp)
    err, got = flow("rr_repair", tp)
    check("rr_repair", not err and content_ok(got), "err=%s files=%s" % (err, sorted(got)))
    os.remove(tp)

    a2 = rar("R2", ["-m0"])
    tp = m.merge(txt_for(91), a2)
    break_payload(tp)
    err, got = flow("rr_no_record_fails", tp)
    check("rr_no_record_fails", err is not None and not got,
          "err=%s files=%s" % (err, sorted(got)))
    os.remove(tp)

    a3 = rar("R3", ["-m0", "-v100k", "-rr5p"])
    if not a3:
        skip("rr_repair_multivol")
    else:
        break_file(os.path.join(TW, "R3.part2.rar"), 300)
        tp = m.merge(txt_for(92), a3)
        err, got = flow("rr_repair_multivol", tp)
        check("rr_repair_multivol", not err and content_ok(got),
              "err=%s files=%s" % (err, sorted(got)))
        os.remove(tp)

    clean_prefix("R4")
    rv = subprocess.run([RAR, "a", "-ibck", "-ep", "-y", "-m0", "-v100k", "-rv2",
                         os.path.join(TW, "R4.rar")] + [n for n, _ in ENTRIES],
                        cwd=SRCD, capture_output=True, timeout=300)
    p1 = os.path.join(TW, "R4.part1.rar")
    if rv.returncode != 0 or not os.path.isfile(p1):
        skip("rev_restore_missing")
    else:
        os.remove(os.path.join(TW, "R4.part2.rar"))
        tp = m.merge(txt_for(93), p1)
        err, got = flow("rev_restore_missing", tp)
        check("rev_restore_missing", not err and content_ok(got),
              "err=%s files=%s" % (err, sorted(got)))
        os.remove(tp)

try:
    app.destroy()
except Exception:
    pass

print("=" * 50)
print("PASS=%d FAIL=%d SKIP=%d" % (len(PASS), len(FAIL), len(SKIP)))
for name, info in FAIL:
    print("  FAILED: %s  %s" % (name, info))
shutil.rmtree(TW, ignore_errors=True)
sys.exit(1 if FAIL else 0)
