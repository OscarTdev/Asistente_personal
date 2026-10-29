import re

path = 'src/pages/ServiciosPage.tsx'
with open(path, 'r', encoding='utf-8') as fp:
    content = fp.read()

# Fix Switch onChange handlers - add boolean type
content = re.sub(r'onChange=\{(value) =>', 'onChange={(value: boolean) =>', content)

# Fix modules.filter(...).map((module: string) -> modules.filter(...).map((module: Module)
content = re.sub(r'\.map\(\(module: string\) =>', '.map((module: Module) =>', content)

with open('src/pages/ServiciosPage.tsx', 'w', encoding='utf-8') as fp:
    fp.write(content)
print('Fixed ServiciosPage.tsx map callbacks')