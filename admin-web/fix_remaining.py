import re

# Fix RemindersPage.tsx
path = 'src/pages/RemindersPage.tsx'
with open(path, 'r', encoding='utf-8') as fp:
    content = fp.read()

# Fix historyItems.map((reminder: string) -> historyItems.map((reminder: Reminder)
content = re.sub(r'historyItems\.slice\(0, 20\)\.map\(\(reminder: string\) =>', 'historyItems.slice(0, 20).map((reminder: Reminder) =>', content)

with open(path, 'w', encoding='utf-8') as fp:
    fp.write(content)
print('Fixed RemindersPage.tsx')

# Fix ServiciosPage.tsx Switch onChange handlers
path = 'src/pages/ServiciosPage.tsx'
with open(path, 'r', encoding='utf-8') as fp:
    content = fp.read()

# Fix Switch onChange handlers - add boolean type
content = re.sub(r'onChange=\{(value) =>', 'onChange={(value: boolean) =>', content)

with open(path, 'w', encoding='utf-8') as fp:
    fp.write(content)
print('Fixed ServiciosPage.tsx Switch handlers')

# Fix ServiceDataPage.tsx map callbacks
path = 'src/pages/ServiceDataPage.tsx'
with open(path, 'r', encoding='utf-8') as fp:
    content = fp.read()

# Fix columns.map((i: string) -> columns.map((i: number)
content = re.sub(r'columns\.map\(\(i: string\) =>', 'columns.map((i: number) =>', content)
content = re.sub(r'columns\.map\(\(col: string\) =>', 'columns.map((col: Column) =>', content)

with open(path, 'w', encoding='utf-8') as fp:
    fp.write(content)
print('Fixed ServiceDataPage.tsx')

print('Done')