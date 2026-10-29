import os
import re

for root, dirs, files in os.walk('src/pages'):
    for f in files:
        if f.endswith('.tsx'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as fp:
                content = fp.read()

            original = content

            # Fix onChange handlers that use setState directly
            # Pattern: onChange={setName} -> onChange={(e) => setName(e.target.value)}
            content = re.sub(
                r'onChange=\{set(\w+)\}',
                r'onChange={(e) => set\1(e.target.value)}',
                content
            )
            content = re.sub(
                r'onChange=\{set(\w+)\}',
                r'onChange={(e) => set\1(e.target.value)}',
                content
            )

            # Pattern: onChange={(e) => setName(e)} -> onChange={(e) => setName(e.target.value)}
            content = re.sub(
                r'onChange=\{\(e\) => set(\w+)\(e\)\}',
                r'onChange={(e) => set\1(e.target.value)}',
                content
            )

            # Fix implicit any in map callbacks
            # tags.map((tag) => ...) -> tags.map((tag: string) => ...)
            content = re.sub(r'\.map\(\((\w+)\) =>', r'.map((\1: string) =>', content)
            content = re.sub(r'\.map\(\((\w+)\) =>', r'.map((\1: string) =>', content)

            # contact.tags.map((tag) => ...
            content = re.sub(r'contact\.tags\.map\(\((\w+)\) =>', r'contact.tags.map((\1: string) =>', content)

            # notesQuery.data?.map((note) => ...
            content = re.sub(r'notesQuery\.data\?\.map\(\((\w+)\) =>', r'notesQuery.data?.map((\1: any) =>', content)

            # chat.data?.pages[0]?.items.map((message) => ...
            content = re.sub(r'chat\.data\?\.pages\[0\]\?\.items\.map\(\((\w+)\) =>', r'chat.data?.pages[0]?.items.map((\1: any) =>', content)

            # data.items.map((contact) => ...
            content = re.sub(r'data\.items\.map\(\((\w+)\) =>', r'data.items.map((\1: any) =>', content)

            if content != original:
                with open(path, 'w', encoding='utf-8') as fp:
                    fp.write(content)
                print('Fixed handlers: ' + path)

print('Done')