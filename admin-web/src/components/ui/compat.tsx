/*
 * Compatibilidad con componentes legacy → shadcn/ui
 * Permite migrar gradualmente sin reescribir todas las páginas.
 */
import * as React from 'react'
import { Button as ShadcnButton, ButtonProps } from './button'
import { Input as ShadcnInput } from './input'
import { Switch as ShadcnSwitch } from './switch'
import { Label } from './label'
import { Modal as ShadcnModal } from './modal'
import { ErrorSlip as ShadcnErrorSlip } from './error-slip'
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from './card'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell, TableCaption } from './table'
import { Badge } from './badge'
import { Avatar, AvatarImage, AvatarFallback } from './avatar'
import { ScrollArea } from './scroll-area'
import { Separator } from './separator'
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from './tooltip'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator } from './dropdown-menu'
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from './select'
import { Tabs, TabsList, TabsTrigger, TabsContent } from './tabs'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger } from './dialog'
import { Sheet, SheetTrigger, SheetContent, SheetHeader, SheetTitle, SheetDescription } from './sheet'

// ── Button wrapper (acepta variant, size igual que shadcn) ──
export const Button = ShadcnButton

// ── Input wrapper (mapea onChangeValue → onChange, soporta ambos) ──
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  onChangeValue?: (value: string) => void
  value?: string
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ onChangeValue, value, onChange, ...props }, ref) => {
    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = e.target.value
      // Call both handlers: onChange receives event, onChangeValue receives string
      onChange?.(e)
      onChangeValue?.(val)
    }
    return <ShadcnInput ref={ref} value={value} onChange={handleChange} {...props} />
  }
)
Input.displayName = 'Input'

// ── Switch wrapper (mismo API) ──
export const Switch = ShadcnSwitch

// ── Modal wrapper (mismo API) ──
export const Modal = ShadcnModal

// ── ErrorSlip wrapper (mismo API, sin onDismiss) ──
export const ErrorSlip = ShadcnErrorSlip

// ── Re-exports directos ──
export {
  Label,
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
  TableCaption,
  Badge,
  Avatar,
  AvatarImage,
  AvatarFallback,
  ScrollArea,
  Separator,
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogTrigger,
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
}