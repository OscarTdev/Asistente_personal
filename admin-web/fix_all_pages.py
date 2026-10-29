import os
import re

for root, dirs, files in os.walk('src/pages'):
    for f in files:
        if f.endswith('.tsx'):
            path = os.path.join(root, f)
            with open(path, 'r', encoding='utf-8') as fp:
                content = fp.read()

            original = content

            # 1. Fix imports: change from '@/components/ui' to individual component imports
            # Replace barrel import with individual imports
            barrel_pattern = r"import\s+\{([^}]+)\}\s+from\s+['\"]@/components/ui['\"]"
            def replace_barrel(match):
                imports = match.group(1).strip()
                # Split imports and generate individual imports
                items = [i.strip() for i in imports.split(',')]
                lines = []
                for item in items:
                    if item in ['Button', 'ButtonProps']:
                        lines.append('import { Button } from "@/components/ui/button"')
                    elif item in ['Input']:
                        lines.append('import { Input } from "@/components/ui/input"')
                    elif item in ['Switch']:
                        lines.append('import { Switch } from "@/components/ui/switch"')
                    elif item in ['Modal']:
                        lines.append('import { Modal } from "@/components/ui/modal"')
                    elif item in ['ErrorSlip']:
                        lines.append('import { ErrorSlip } from "@/components/ui/error-slip"')
                    elif item in ['Card', 'CardHeader', 'CardTitle', 'CardContent', 'CardFooter']:
                        lines.append('import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card"')
                    elif item in ['Table', 'TableHeader', 'TableBody', 'TableRow', 'TableHead', 'TableCell', 'TableCaption']:
                        lines.append('import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from "@/components/ui/table"')
                    elif item in ['Badge']:
                        lines.append('import { Badge } from "@/components/ui/badge"')
                    elif item in ['Avatar', 'AvatarImage', 'AvatarFallback']:
                        lines.append('import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar"')
                    elif item in ['ScrollArea']:
                        lines.append('import { ScrollArea } from "@/components/ui/scroll-area"')
                    elif item in ['Separator']:
                        lines.append('import { Separator } from "@/components/ui/separator"')
                    elif item in ['Tooltip', 'TooltipTrigger', 'TooltipContent', 'TooltipProvider']:
                        lines.append('import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from "@/components/ui/tooltip"')
                    elif item in ['DropdownMenu', 'DropdownMenuTrigger', 'DropdownMenuContent', 'DropdownMenuItem', 'DropdownMenuSeparator']:
                        lines.append('import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator } from "@/components/ui/dropdown-menu"')
                    elif item in ['Select', 'SelectTrigger', 'SelectValue', 'SelectContent', 'SelectItem']:
                        lines.append('import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select"')
                    elif item in ['Tabs', 'TabsList', 'TabsTrigger', 'TabsContent']:
                        lines.append('import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"')
                    elif item in ['Dialog', 'DialogContent', 'DialogHeader', 'DialogTitle', 'DialogFooter', 'DialogTrigger']:
                        lines.append('import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from "@/components/ui/dialog"')
                    elif item in ['Sheet', 'SheetTrigger', 'SheetContent', 'SheetHeader', 'SheetTitle', 'SheetDescription']:
                        lines.append('import { Sheet, SheetTrigger, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet"')
                    elif item in ['Label']:
                        lines.append('import { Label } from "@/components/ui/label"')
                    elif item in ['Form', 'FormField', 'FormItem', 'FormLabel', 'FormControl', 'FormMessage']:
                        lines.append('import { Form, FormField, FormItem, FormLabel, FormControl, FormMessage } from "@/components/ui/form"')
                    elif item in ['Tooltip', 'TooltipTrigger', 'TooltipContent', 'TooltipProvider']:
                        pass  # already handled
                    else:
                        # Keep as is for unknown
                        lines.append(f'import {{ {item} }} from "@/components/ui/{item.lower()}"')
                return '\n'.join(lines)

            content = re.sub(barrel_pattern, replace_barrel, content)

            # 2. Fix Input: onChangeValue -> onChange
            content = re.sub(r'onChangeValue=', 'onChange=', content)

            # 3. Fix ErrorSlip: remove onDismiss prop
            content = re.sub(r'\s+onDismiss=\{\(\) => [^}]+\}', '', content)
            content = re.sub(r'<ErrorSlip([^>]*)\s+onDismiss=\{\(\) => [^}]+\}', r'<ErrorSlip\1', content)

            # 4. Fix Button variant/size - these ARE valid in shadcn/ui, keep them
            # The errors might be type resolution issues

            # 5. Fix ServiciosPage IconEnter -> IconArrowLeft
            content = content.replace('IconEnter', 'IconArrowLeft')

            # 6. Fix RemindersPage Button size prop (size IS valid in shadcn/ui)
            # Keep as is

            # 7. Fix QuoteDetailPage Input onChange handler
            # The issue is onChangeValue was replaced with onChange but the handler expects (value: string) => void
            # Need to fix the handler to use e.target.value
            content = re.sub(
                r'onChange=\{(?:\(e\) => )?set(\w+)\(e\.target\.value\)\}',
                r'onChange={(e) => set\1(e.target.value)}',
                content
            )

            if content != original:
                with open(path, 'w', encoding='utf-8') as fp:
                    fp.write(content)
                print('Fixed: ' + path)

print('Done')