import re

path = 'src/pages/ServiciosPage.tsx'
with open(path, 'r', encoding='utf-8') as fp:
    content = fp.read()

# Fix Switch onChange handlers - add boolean type
content = re.sub(r'onChange=\{(value) =>', 'onChange={(value: boolean) =>', content)

# Fix modules.map((module: string) -> modules.map((module: Module)
content = re.sub(r'modules\?\.map\(\(module: string\) =>', 'modules?.map((module: Module) =>', content)

# Fix items.map((i: string) -> items.map((i: any)
content = re.sub(r'items\.map\(\(i: string\) =>', 'items.map((i: any) =>', content)

# Fix [0, 1, 2].map((index: string) -> [0, 1, 2].map((index: number)
content = re.sub(r'\[0, 1, 2\]\.map\(\(index: string\) =>', '[0, 1, 2].map((index: number) =>', content)

# Fix modules.map((module: string) -> modules.map((module: Module)
content = re.sub(r'modules\.map\(\(module: string\) =>', 'modules.map((module: Module) =>', content)

with open('src/pages/ServiciosPage.tsx', 'w', encoding='utf-8') as fp:
    fp.write(content)
print('Fixed ServiciosPage.tsx final')