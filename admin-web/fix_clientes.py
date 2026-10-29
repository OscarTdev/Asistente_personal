import re

path = 'src/pages/ClientesPage.tsx'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the barrel import
content = re.sub(r'\} from \'..\/..\/components\/ui\'', '} from "@/components/ui"', content)
content = re.sub(r'\} from "..\/..\/components\/ui"', '} from "@/components/ui"', content)
content = re.sub(r'from \'..\/..\/components\/ui/icons\'', 'from "@/components/ui/icons"', content)
content = re.sub(r'from "..\/..\/components\/ui/icons"', 'from "@/components/ui/icons"', content)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed ClientesPage.tsx')