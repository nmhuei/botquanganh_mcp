import sys, json

# Galois Field GF(2^8) with Rijndael polynomial 0x11B
POLY = 0x11B

def gf_mul(a, b):
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= (POLY & 0xFF)
        b >>= 1
    return p

# Secret key in GF(256)
SECRET_KEY = 0x9D

def compute_mac(msg_bytes: bytes, key: int = SECRET_KEY) -> int:
    """Polynomial evaluation: Tag = sum_{i=0}^{n} (msg[i] ^ key) * x^{i+1} in GF(2^8) with fixed x=0x03"""
    x = 0x03
    tag = 0
    cur_x = x
    for b in msg_bytes:
        term = gf_mul(b ^ key, cur_x)
        tag ^= term
        cur_x = gf_mul(cur_x, x)
    return tag

def verify_token(user: str, role: str, tag: int) -> bool:
    payload = f"user={user}&role={role}".encode()
    return compute_mac(payload) == tag

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python3 server_crypto.py <user> <role> <tag_hex>")
        sys.exit(1)
    u, r, t = sys.argv[1], sys.argv[2], int(sys.argv[3], 16)
    if verify_token(u, r, t):
        if r == "admin":
            print("FLAG{galois_field_mac_forgery_solved_7718}")
        else:
            print(f"Welcome {u}, role is {r}")
        sys.exit(0)
    else:
        print("INVALID_TAG")
        sys.exit(2)
