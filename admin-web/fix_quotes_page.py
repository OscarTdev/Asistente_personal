import re

path = 'src/pages/QuotesPage.tsx'
with open(path, 'r', encoding='utf-8') as fp:
    content = fp.read()

# Fix response.suggestions.map((suggestion: string) -> response.suggestions.map((suggestion: ExtractedSuggestion)
content = re.sub(r'response\.suggestions\.map\(\(suggestion: string\) =>', 'response.suggestions.map((suggestion: ExtractedSuggestion) =>', content)

# Fix items.map((index: string) -> items.map((index: number)
content = re.sub(r'items\.map\(\(index: string\) =>', 'items.map((index: number) =>', content)

# Fix quotations.map((quote: string) -> quotations.map((quote: Quote)
content = re.sub(r'quotations\.map\(\(quote: string\) =>', 'quotations.map((quote: Quote) =>', content)

# Fix items.map((quote: string) -> items.map((quote: Quote)
content = re.sub(r'items\.map\(\(quote: string\) =>', 'items.map((quote: Quote) =>', content)

with open(path, 'w', encoding='utf-8') as fp:
    fp.write(content)
print('Fixed QuotesPage.tsx map callbacks')

# Fix RemindersPage.tsx - add Reminder import
path = 'src/pages/RemindersPage.tsx'
with open(path, 'r', encoding='utf-8') as fp:
    content = fp.read()

# Add Reminder import if not present
if 'import { Reminder } from' not in content:
    content = content.replace(
        "import { useState } from 'react'",
        "import { useState } from 'react'\nimport { Reminder } from '../../types'"
    )

# Fix map callbacks
content = re.sub(r'reminders\.map\(\(reminder: string\) =>', 'reminders.map((reminder: Reminder) =>', content)
content = re.sub(r'historyItems\.slice\(0, 20\)\.map\(\(reminder: string\) =>', 'historyItems.slice(0, 20).map((reminder: Reminder) =>', content)
content = re.sub(r'reminders\.filter\(\(reminder: string\) =>', 'reminders.filter((reminder: Reminder) =>', content)

with open(path, 'w', encoding='utf-8') as fp:
    fp.write(content)
print('Fixed RemindersPage.tsx')

# Fix ServiceDataPage.tsx
path = 'src/pages/ServiceDataPage.tsx'
with open(path, 'r', encoding='utf-8') as fp:
    content = fp.read()

content = re.sub(r'columns\.map\(\(i: string\) =>', 'columns.map((i: number) =>', content)
content = re.sub(r'columns\.map\(\(col: string\) =>', 'columns.map((col: Column) =>', content)

with open(path, 'w', encoding='utf-8') as fp:
    fp.write(content)
print('Fixed ServiceDataPage.tsx')

# Fix ServiciosPage.tsx Switch handlers
path = 'src/pages/ServiciosPage.tsx'
with open(path, 'r', encoding='utf-8') as fp:
    content = fp.read()

content = re.sub(r'onChange=\{(value) =>', 'onChange={(value: boolean) =>', content)

with open(path, 'w', encoding='utf-8') as fp:
    fp.write(content)
print('Fixed ServiciosPage.tsx Switch handlers')

print('Done')