import os
import re

for root, dirs, files in os.walk('src/pages'):
    for f in files:
        if f.endswith('.tsx'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as fp:
                content = fp.read()

            original = content

            # Fix Input: onChangeValue -> onChange
            content = re.sub(r'onChangeValue=', 'onChange=', content)

            # Fix ErrorSlip: remove onDismiss prop
            content = re.sub(r'\s+onDismiss=\{\(\) => [^}]+\}', '', content)
            content = re.sub(r'\s+onDismiss=\{\(\) => [^}]+\}', '', content)

            # Fix ErrorSlip: onDismiss in JSX
            content = re.sub(r'<ErrorSlip([^>]*)\s+onDismiss=\{\(\) => [^}]+\}', r'<ErrorSlip\1', content)

            # Fix Switch: ensure it's used correctly (no changes needed)

            # Fix Button variant/size - these should work with shadcn/ui
            # The errors might be due to type resolution, not actual prop issues

            # Fix RemindersPage Button size prop
            content = re.sub(r'<Button([^>]*)\s+size="([^"]*)"', r'<Button\1 size="\2"', content)

            # Fix ServiciosPage IconEnter -> IconArrowLeft or similar
            content = content.replace('IconEnter', 'IconArrowLeft')

            if content != original:
                with open(path, 'w', encoding='utf-8') as fp:
                    fp.write(content)
                print('Fixed: ' + path)

print('Done')