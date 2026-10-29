import re

path = 'src/pages/ServiciosPage.tsx'
with open(path, 'r', encoding='utf-8') as fp:
    content = fp.read()

# Fix plans.map((p: string) => -> plans.map((p: {key: string, label: string}) =>
content = re.sub(r'plans\.map\(\(p: string\) =>', 'plans.map((p: {key: string, label: string}) =>', content)

# Fix data.map((i: string) => -> data.map((i: PlanEntitlementItem) =>
content = re.sub(r'\(data \?\? \[\]\)\.map\(\(i: string\) =>', '(data ?? []).map((i: PlanEntitlementItem) =>', content)
content = re.sub(r'\(data \?\? \[\]\)\.map\(\(i: string\) =>', '(data ?? []).map((i: PlanEntitlementItem) =>', content)

# Fix new Set((data ?? []).map((i: string) => i.module_key)) -> new Set((data ?? []).map((i: PlanEntitlementItem) => i.module_key))
content = re.sub(r'new Set\(\(data \?\? \[\]\)\.map\(\(i: string\) => i\.module_key\)\)', 'new Set((data ?? []).map((i: PlanEntitlementItem) => i.module_key))', content)

# Fix [0, 1, 2].map((index: string) => -> [0, 1, 2].map((index: number) =>
content = re.sub(r'\[0, 1, 2\]\.map\(\(index: string\) =>', '[0, 1, 2].map((index: number) =>', content)

# Fix modules?.map((module: string) => -> modules?.map((module: Module) =>
content = re.sub(r'modules\?\.map\(\(module: string\) =>', 'modules?.map((module: Module) =>', content)

# Fix items.map((i: string) => -> items.map((i: any) =>
content = re.sub(r'items\.map\(\(i: string\) =>', 'items.map((i: any) =>', content)

# Fix plans.map((p: string) => -> plans.map((p: {key: string, label: string}) =>
content = re.sub(r'plans\.map\(\(p: string\) =>', 'plans.map((p: {key: string, label: string}) =>', content)

with open('src/pages/ServiciosPage.tsx', 'w', encoding='utf-8') as fp:
    fp.write(content)
print('Fixed ServiciosPage.tsx')