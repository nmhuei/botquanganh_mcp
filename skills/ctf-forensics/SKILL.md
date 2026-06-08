# ctf-forensics

## Description

Forensics skill — disk images, memory dumps, PCAPs, logs, steganography, image/audio
analysis, archives, document formats, deleted files, malware artifacts, and layered
encoding found inside files.

Use this skill when the flag is hidden in artifacts rather than exploited from a
live service.

## Prerequisites

```bash
apt-get install -y file binwalk foremost testdisk sleuthkit exiftool imagemagick ffmpeg steghide zsteg tshark pcapfix john hashcat unzip p7zip-full
python3 -m pip install pillow numpy matplotlib scapy volatility3 oletools yara-python pefile --break-system-packages
```

Optional:

```bash
gem install zsteg
```

## Recon Checklist

```bash
mkdir -p recon artifacts_extracted evidence
file artifacts/* | tee recon/file.txt
sha256sum artifacts/* | tee evidence/input-sha256.txt
strings -a artifacts/* | tee recon/strings.txt
strings -a artifacts/* | grep -iE 'flag|ctf|password|secret|key'
exiftool artifacts/* | tee recon/exiftool.txt
binwalk artifacts/* | tee recon/binwalk.txt
```

## Triage by File Type

| Artifact | First tools |
|----------|-------------|
| image | exiftool, binwalk, zsteg, steghide, identify |
| audio | exiftool, strings, spectrogram, sox/ffmpeg |
| pcap | tshark, wireshark, scapy, foremost |
| memory dump | volatility3 |
| disk image | mmls, fls, icat, strings |
| archive | 7z, zipinfo, john/hashcat |
| Office/PDF | oletools, unzip, exiftool, strings |
| unknown binary blob | file, xxd, binwalk, entropy |

## Image Stego

```bash
exiftool image.png
zsteg -a image.png
binwalk -e image.png
steghide info image.jpg
steghide extract -sf image.jpg
identify -verbose image.png
convert image.png -separate channel_%d.png
```

Check:

- metadata comments
- LSB channels
- appended archive
- alpha channel
- palette ordering
- QR/barcode fragments
- dimensions/least significant pixels
- color-plane differences

Python pixel scan:

```python
from PIL import Image
img = Image.open("artifacts/image.png").convert("RGBA")
bits = []
for r,g,b,a in img.getdata():
    bits.append(r & 1)
out = bytes(int("".join(map(str,bits[i:i+8])),2) for i in range(0,len(bits)-7,8))
print(out[:500])
```

## Audio

```bash
file audio.wav
exiftool audio.wav
ffmpeg -i audio.wav recon/audio.png
sox audio.wav -n spectrogram -o recon/spectrogram.png
strings audio.wav | grep -i flag
```

Check:

- spectrogram text
- Morse
- DTMF
- SSTV
- hidden channels
- reversed audio
- LSB samples

## PCAP

```bash
tshark -r capture.pcapng -q -z conv,tcp
tshark -r capture.pcapng -Y 'http' -T fields -e http.host -e http.request.uri
tshark -r capture.pcapng --export-objects http,recon/http-objects
foremost -i capture.pcapng -o recon/foremost
```

Useful filters:

```text
http
dns
tcp.stream eq 0
ftp || ftp-data
smtp || imap || pop
tls.handshake.extensions_server_name
frame contains "flag"
```

Extract TCP stream:

```bash
tshark -r capture.pcapng -q -z follow,tcp,ascii,0
```

## Memory Forensics

```bash
vol -f mem.raw windows.info
vol -f mem.raw windows.pslist
vol -f mem.raw windows.cmdline
vol -f mem.raw windows.filescan | grep -i flag
vol -f mem.raw windows.dumpfiles --pid <PID> --dump-dir recon/dump
strings -a mem.raw | grep -iE 'flag|ctf|password'
```

Linux/mac profiles vary; fall back to `strings`, `binwalk`, and file carving.

## Disk Images

```bash
mmls disk.img
fls -r -o <offset> disk.img | tee recon/fls.txt
icat -o <offset> disk.img <inode> > recon/recovered.bin
tsk_recover -o <offset> disk.img recon/recovered_files
```

Check deleted files, browser history, shell history, SSH keys, `.git`, recycle bin.

## Archives / Passwords

```bash
zipinfo file.zip
zip2john file.zip > recon/hash.txt
john recon/hash.txt --wordlist=/usr/share/wordlists/rockyou.txt
7z x file.7z
```

## Documents

```bash
exiftool doc.pdf
pdfimages -all doc.pdf recon/pdfimg
strings doc.pdf | grep -i flag
olevba document.docm
unzip -l document.docx
unzip document.docx -d recon/docx
grep -RniE 'flag|ctf|secret' recon/docx
```

## Verify

A forensics flag is valid only when:

- The extraction path is reproducible from the original artifact, and
- The recovered text matches flag format, and
- It is not a decoy found by naive `strings` unless corroborated by context.

Save command transcript and hashes:

```bash
sha256sum artifacts/* evidence/* > evidence/SHA256SUMS
```

## Pivot Rules

- Extracted binary requires analysis → `ctf-reverse`
- Extracted service/source requires exploitation → `ctf-web` or `ctf-pwn`
- Extracted ciphertext/keys → `ctf-crypto`
- OSINT/geolocation from media → `ctf-osint`
