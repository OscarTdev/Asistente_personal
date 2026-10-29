import os
import re

named_exports = {
    'card': ['Card', 'CardHeader', 'CardTitle', 'CardContent', 'CardFooter'],
    'button': ['Button'],
    'input': ['Input'],
    'modal': ['Modal'],
    'switch': ['Switch'],
    'error-slip': ['ErrorSlip'],
    'dialog': ['Dialog', 'DialogContent', 'DialogHeader', 'DialogTitle', 'DialogFooter', 'DialogTrigger'],
    'form': ['Form', 'FormField', 'FormItem', 'FormLabel', 'FormControl', 'FormMessage'],
    'select': ['Select', 'SelectTrigger', 'SelectValue', 'SelectContent', 'SelectItem'],
    'label': ['Label'],
    'tabs': ['Tabs', 'TabsList', 'TabsTrigger', 'TabsContent'],
    'table': ['Table', 'TableHeader', 'TableBody', 'TableRow', 'TableHead', 'TableCell', 'TableCaption'],
    'tooltip': ['Tooltip', 'TooltipTrigger', 'TooltipContent', 'TooltipProvider'],
    'dropdown-menu': ['DropdownMenu', 'DropdownMenuTrigger', 'DropdownMenuContent', 'DropdownMenuItem', 'DropdownMenuSeparator'],
    'avatar': ['Avatar', 'AvatarImage', 'AvatarFallback'],
    'badge': ['Badge'],
    'scroll-area': ['ScrollArea'],
    'separator': ['Separator'],
    'sheet': ['Sheet', 'SheetTrigger', 'SheetContent', 'SheetHeader', 'SheetTitle', 'SheetDescription'],
    'icons': [],
}

for root, dirs, files in os.walk('src/pages'):
    for f in files:
        if f.endswith('.tsx'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as fp:
                content = fp.read()

            original = content

            for module, exports in named_exports.items():
                if not exports:
                    continue
                pattern = r'import\s+(\w+)\s+from\s+[\'"](\.\./components/ui/' + module + r')[\'"]'
                matches = list(re.finditer(pattern, content))
                for match in reversed(matches):
                    imported_name = match.group(1)
                    if imported_name in exports:
                        old = match.group(0)
                        new = 'import { ' + imported_name + ' } from "' + match.group(2) + '"'
                        content = content[:match.start()] + new + content[match.end():]

            # Fix icons import
            content = re.sub(r'from [\'"]\.\./components/ui/icons[\'"]', 'from "@/components/ui/icons"', content)
            content = re.sub(r'from [\'"]@/components/ui[\'"]', 'from "@/components/ui"', content)

            if content != original:
                with open(path, 'w', encoding='utf-8') as fp:
                    fp.write(content)
                print('Fixed: ' + path)

print('Done')