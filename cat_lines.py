import sys
with open(sys.argv[1], 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if i == 49:
        print(f"Line {i+1}: {repr(line)}")
