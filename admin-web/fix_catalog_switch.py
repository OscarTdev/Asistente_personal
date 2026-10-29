import re

path = 'src/pages/CatalogPage.tsx'
with open(path, 'r', encoding='utf-8') as fp:
    content = fp.read()

# Fix the Switch
content = re.sub(
    r'<Switch checked=\{showInactive\} onChange=\{\(e\) => setShowInactive\(e\.target\.value\)\} label="Mostrar ítems inactivos" />',
    '<Switch checked={showInactive} onCheckedChange={(e) => setShowInactive(e.target.checked)} />',
    content
)

with open(path, 'w', encoding='utf-8') as fp:
    fp.write(content)
print('Fixed CatalogPage.tsx Switch')