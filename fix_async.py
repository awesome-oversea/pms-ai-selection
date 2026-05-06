import re

def fix_await_in_sync_func(content):
    lines = content.split('\n')
    result = []
    in_test_func = False
    added_asyncio = False

    for line in lines:
        stripped = line.strip()

        if re.match(r'def test_\w+\(self\):', stripped):
            in_test_func = True
            added_asyncio = False
            result.append(line)
            continue

        if in_test_func and stripped and not stripped.startswith(('#', '"""', "'''")):
            if stripped.startswith('def ') or re.match(r'class \w+', stripped):
                in_test_func = False
                added_asyncio = False
                result.append(line)
                continue

        if in_test_func and 'await ' in line and not added_asyncio:
            indent = len(line) - len(line.lstrip())
            result.append(' ' * indent + 'import asyncio')
            added_asyncio = True

        if in_test_func and 'await ' in line:
            result.append(line.replace('await ', 'asyncio.run(', 1).rstrip() + ')')
            continue

        result.append(line)

    return '\n'.join(result)


files = [
    r'D:\Project\fms\tests\test_d22_d24.py',
    r'D:\Project\fms\tests\test_d4_d6.py',
]

for fpath in files:
    with open(fpath, 'r', encoding='utf-8') as f:
        content = f.read()

    fixed = fix_await_in_sync_func(content)

    with open(fpath, 'w', encoding='utf-8') as f:
        f.write(fixed)

    print(f'Fixed: {fpath}')
