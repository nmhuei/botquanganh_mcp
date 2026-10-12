import json
import codecs

with open('cipher.txt', 'r', encoding='utf-8') as f:
    cipher = f.read().strip()

flag = codecs.decode(cipher, 'rot_13')
result = {'status': 'solved', 'flag': flag}

with open('solution.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, indent=2)

print(json.dumps(result))
