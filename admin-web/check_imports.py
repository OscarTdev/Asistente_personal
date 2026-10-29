import os
import re

for root, dirs, files in os.walk('src/pages'):
    for f in files:
        if f.endswith('.tsx'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as fp:
                content = fp.read()
            if '@/components/ui' in content:
                if re.search(r'import\s+\{.*\}\s+from\s+[\'"]@/components/ui[\'"]', content):
                    print('Has barrel import: ' + path)