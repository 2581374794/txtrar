# txtrar工具能做什么？

把 **一个 txt** （比如压缩包的压缩密码） 和 **一个压缩包**合成单个 `.txtrar` 文件，需要时再拆开、按原格式解压。

本工具自带txt查看功能和压缩包解压功能。

本工具为单文件的 Windows exe，约 10 MB，免安装、无外部依赖，rar 引擎内嵌。

文件格式：
```
[ txt 字节 ] + "\n\n-----RAR START-----\n"（22 字节）+ [ 压缩包字节 ]
```


## 用法

**合成**：选 txt + 选压缩包 → 合成。也可把两个文件一起拖到 exe 图标上。

**解压**：选 `.txtrar` → 查看txt获得密码（若有） → 填密码（若有）→ 解压。

合成和解压的文件均输出到exe的原目录文件夹下，`exe目录\<txt名>+<压缩包名>.txtrar`、`exe目录\<原名>_解压\`。

分卷场景下，被合成进 `.txtrar` 的必须是**第一分卷**，其余分卷放在 `.txtrar`（或 exe）同一目录。

## 下载

Windows exe 可在仓库根目录直接获取，也可到 **Releases** 下载发布版本：<https://github.com/2581374794/txtrar/releases>

## 特性

- **双格式产物**
- - 改名 `.txt` 可直接阅读（windows的记事本有打开文件的体积上限，超过1个g的文件无法用修改txt后缀的方式直接用记事本查看；大文件可以用本工具自带的查看功能查看）
- - 改名 `.rar` / `.zip` / `.7z` 可被对应软件直接打开（本工具也内置解压功能，可以随压缩包一并分发）
- **附带 zip / 7z** — 含 WinZip AES、7z 头部加密、分卷
- - **损坏自愈** — rar 带恢复记录时自动修复；带恢复卷时自动重建缺失分卷

## 支持范围

| 格式 | 压缩算法 | 加密 | 分卷 | 其它 |
|---|---|---|---|---|
| **rar** | RAR5 / RAR4，`-m0`~`-m5`，**固实 `-s`** | `-p` 数据加密、**`-hp` 头部加密** | 支持（三种命名） | **恢复记录 `-rr` 自动修复**、**恢复卷 `.rev` 自动重建** |
| zip | Deflate / Store / BZip2 / LZMA | ZipCrypto、**AES-128 / 192 / 256** | 支持（两种命名） | Zip64 |
| 7z | LZMA / LZMA2 / BZip2 / Deflate / Copy / **Zstd**、Delta、BCJ、ARM、ARMT、PPC、SPARC、IA64、PPMd | `-p` 数据加密、**`-mhe=on` 头部加密** | 支持 | — |

三种格式均支持中文 / 日文文件名，并有真实字节进度条。空密码、错密码、非首卷、分卷缺失、文件损坏都有明确提示。

### 恢复能力

- 修复只作用于**解压后的副本**，不改动压缩包原文件
- 只在 `rar r` **真正用上恢复记录**时才采纳结果（产物为 `fixed.*`），不存在「假装修好了」的情况
- 分卷场景每个分卷各自带恢复记录，中间某卷损坏同样能救；`-hp` 加密包无需密码也能修
- 上限：只能修复恢复记录容量之内的损坏（`-rr5p` 约覆盖包体积的 5%）

### 不支持的算法

- zip：Deflate64、PPMd、JPEG、WavPack 等 → 报 `zip使用了不支持的压缩方式`
- 7z：BCJ2、ARM64、RISCV、Swap、Brotli 等 → 报 `7z使用了本工具不支持的压缩算法，请改用 7-Zip / WinRAR 解压。`

## 限制

- 只支持 rar / zip / 7z；不支持 tar / gz / xz / bz2 / iso / cab 等
- 只能**解压**，不能创建压缩包
- 加密包只接受**一个密码**，无字典攻击、无暴力破解
- **没有恢复记录**的损坏包无法修复（rar 也一样），只能另找完好副本
- 分卷必须合成第一分卷；其余分卷须与 `.txtrar`（或 exe）同目录
- 解压输出目录固定，不可自定义
- Windows 专用

## 体积上限

工具本身不设上限 —— 合成、扫描、拷贝、解密、分卷拼接全部 4 MB 分块流式处理，不把整个文件读进内存。

| 环节 | 上限 |
|---|---|
| 文件系统 | FAT32 单文件 4 GB；NTFS / exFAT 无实际限制 |
| rar | RAR5 无实际限制；RAR4 单文件约 8.58 GB |
| zip | 已支持 Zip64；非 Zip64 的 zip 按规范本身就不可能超过 4 GB |
| 7z | 受内存限制，按压缩时的字典大小分配（如 `-md=1024m` 约需 1 GB） |

磁盘峰值占用约为 `txtrar 大小 × 2 + 解压后大小`（解压时会先把载荷复制到 `%TEMP%`）。

## 构建

```bat
cd txtrar工具源码
python -m venv venv
venv\Scripts\pip install pyinstaller py7zr pycryptodomex
venv\Scripts\pyinstaller txtrar工具.spec
```

产物在 `dist\txtrar工具.exe`，`engine\` 下的 `UnRAR.exe` 与 `Rar.exe` 会一并打进 exe。需用 **Python 3.14 + PyInstaller 6.22.3**。

注意：`typing`、`json`、`email`、`urllib` 不能放进 `excludes` —— 依赖链 `py7zr → bcj → importlib.metadata → json/email/csv/inspect → email.utils → urllib.parse`，排除任一环会让 7z 在打包后整体不可用，而源码态看不出来。

## 许可

| 组件 | 用途 | 许可 |
|---|---|---|
| `UnRAR.exe` | rar 解压 | 版权归 Alexander Roshal，**仅可用于解压，不得用于还原 rar 压缩算法** |
| `Rar.exe` | 恢复记录修复（`rar r`） | 版权归 Alexander Roshal，**共享软件**，官方 EULA 规定试用 40 天后需购买授权 |
| [py7zr](https://github.com/miurahr/py7zr) | 7z 解压 | LGPL-2.1+ |
| [pycryptodomex](https://github.com/Legrandin/pycryptodome) | AES zip 解密 | BSD-2-Clause / Public Domain |
| Tcl/Tk | GUI | TCL 风格许可 |
