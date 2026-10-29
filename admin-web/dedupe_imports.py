import os
import re

for root, dirs, files in os.walk('src/pages'):
    for f in files:
        if f.endswith('.tsx'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as fp:
                content = fp.read()

            original = content

            # Deduplicate imports
            lines = content.split('\n')
            seen_imports = set()
            new_lines = []
            for line in lines:
                if line.strip().startswith('import ') and 'from ' in line:
                    # Normalize import line
                    normalized = re.sub(r'\s+', ' ', line.strip())
                    if normalized not in seen_imports:
                        seen_imports.add(normalized)
                        new_lines.append(line)
                else:
                    new_lines.append(line)

            content = '\n'.join(new_lines)

            if content != original:
                with open(path, 'w', encoding='utf-8') as fp:
                    fp.write(content)
                print('Deduped: ' + path)

print('Done')