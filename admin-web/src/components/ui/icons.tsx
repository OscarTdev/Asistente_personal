// Icon components - Lucide React
import { createElement, SVGProps, ReactElement } from 'react'

type IconComponent = (props: SVGProps<SVGSVGElement>) => React.ReactElement

function createIcon(paths: ReactElement | ReactElement[], name: string): IconComponent {
  const children = Array.isArray(paths) ? paths : [paths]
  const Icon = (props: SVGProps<SVGSVGElement>) =>
    createElement('svg', {
      ...props,
      viewBox: '0 0 24 24',
      fill: 'none',
      stroke: 'currentColor',
      strokeWidth: 2,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      children: children,
    })
  Icon.displayName = name
  return Icon
}

// Navigation
export const IconGrid = createIcon(<path d="M3 9h18M3 15h18M3 3h18v18H3z" key="p" />, 'IconGrid')
export const IconChevronLeft = createIcon(<path d="M15 18l-6-6 6-6" key="p" />, 'IconChevronLeft')
export const IconChevronRight = createIcon(<path d="M9 18l6-6-6-6" key="p" />, 'IconChevronRight')
export const IconChevronDown = createIcon(<path d="M6 9l6 6 6-6" key="p" />, 'IconChevronDown')
export const IconChevronUp = createIcon(<path d="M18 15l-6-6-6 6" key="p" />, 'IconChevronUp')
export const IconArrowLeft = createIcon(<path d="M19 12H5M12 19l-7-7 7-7" key="p" />, 'IconArrowLeft')

// Actions
export const IconSearch = createIcon([<circle cx="11" cy="11" r="8" key="c" />, <path d="M21 21l-4.35-4.35" key="p" />], 'IconSearch')
export const IconFilter = createIcon(<polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" key="p" />, 'IconFilter')
export const IconEdit = createIcon([<path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" key="p1" />, <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5a2.121 2.121 0 013 3z" key="p2" />, <path d="M16 15l-2-2" key="p3" />], 'IconEdit')
export const IconTrash2 = createIcon([<polyline points="3 6 5 6 21 6" key="p1" />, <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" key="p2" />, <line x1="10" y1="11" x2="10" y2="17" key="l1" />, <line x1="14" y1="11" x2="14" y2="17" key="l2" />], 'IconTrash2')
export const IconEye = createIcon([<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" key="p" />, <circle cx="12" cy="12" r="3" key="c" />], 'IconEye')
export const IconEyeOff = createIcon([<path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19m-6.72-1.07a3 3 0 11-4.24-4.24" key="p1" />, <line x1="1" y1="1" x2="23" y2="23" key="l1" />], 'IconEyeOff')
export const IconMoreVertical = createIcon([<circle cx="12" cy="12" r="1" key="c1" />, <circle cx="12" cy="5" r="1" key="c2" />, <circle cx="12" cy="19" r="1" key="c3" />], 'IconMoreVertical')
export const IconX = createIcon([<line x1="18" y1="6" x2="6" y2="18" key="l1" />, <line x1="6" y1="6" x2="18" y2="18" key="l2" />], 'IconX')
export const IconPlus = createIcon([<line x1="12" y1="5" x2="12" y2="19" key="l1" />, <line x1="5" y1="12" x2="19" y2="12" key="l2" />], 'IconPlus')
export const IconMinus = createIcon(<line x1="5" y1="12" x2="19" y2="12" key="l" />, 'IconMinus')
export const IconCheck = createIcon(<polyline points="20 6 9 17 4 12" key="p" />, 'IconCheck')
export const IconDownload = createIcon([<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" key="p1" />, <polyline points="7 10 12 15 17 10" key="p2" />, <line x1="12" y1="15" x2="12" y2="3" key="l" />], 'IconDownload')
export const IconUpload = createIcon([<path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" key="p1" />, <polyline points="17 8 12 3 7 8" key="p2" />, <line x1="12" y1="3" x2="12" y2="15" key="l" />], 'IconUpload')
export const IconSettings = createIcon(<path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-2 2 2 2 0 01-2-2v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83 0 2 2 0 010-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 01-2-2 2 2 0 012-2h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 010-2.83 2 2 0 012.83 0l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 012-2 2 2 0 012 2h.09a1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 0 2 2 0 010 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 012 2 2 2 0 01-2 2h-.09a1.65 1.65 0 00-1.51 1z" key="p" />, 'IconSettings')
export const IconLogout = createIcon([<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" key="p1" />, <polyline points="16 17 21 12 16 7" key="p2" />, <line x1="21" y1="12" x2="9" y2="12" key="l" />], 'IconLogout')
export const IconBell = createIcon([<path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" key="p1" />, <path d="M13.73 21a2 2 0 01-3.46 0" key="p2" />], 'IconBell')
export const IconCalendar = createIcon([<rect x="3" y="4" width="18" height="18" rx="2" ry="2" key="r" />, <line x1="16" y1="2" x2="16" y2="6" key="l1" />, <line x1="8" y1="2" x2="8" y2="6" key="l2" />, <line x1="3" y1="10" x2="21" y2="10" key="l3" />], 'IconCalendar')
export const IconMessageSquare = createIcon(<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" key="p" />, 'IconMessageSquare')
export const IconFileText = createIcon([<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" key="p1" />, <polyline points="14 2 14 8 20 8" key="p2" />, <line x1="16" y1="13" x2="8" y2="13" key="l1" />, <line x1="16" y1="17" x2="8" y2="17" key="l2" />, <polyline points="10 9 9 9 8 9" key="p3" />], 'IconFileText')
export const IconUsers = createIcon([<path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2" key="p1" />, <circle cx="9" cy="7" r="4" key="c" />, <path d="M23 21v-2a4 4 0 00-3-3.87" key="p2" />, <path d="M16 3.13a4 4 0 010 7.75" key="p3" />], 'IconUsers')
export const IconBuilding = createIcon([<rect x="3" y="21" width="18" height="2" rx="1" key="r" />, <path d="M5 21V9l9-6 9 6v12a2 2 0 01-2 2H7a2 2 0 01-2-2V9z" key="p1" />, <path d="M9 21v-8" key="p2" />, <path d="M15 21v-4" key="p3" />], 'IconBuilding')
export const IconCreditCard = createIcon([<rect x="2" y="4" width="20" height="16" rx="2" key="r" />, <line x1="2" y1="10" x2="22" y2="10" key="l" />], 'IconCreditCard')
export const IconWifi = createIcon([<path d="M5 13a10 10 0 0114 0" key="p1" />, <path d="M8.5 16.5a5 5 0 017 0" key="p2" />, <line x1="12" y1="20" x2="12.01" y2="20" key="l" />], 'IconWifi')
export const IconZap = createIcon(<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" key="p" />, 'IconZap')
export const IconShield = createIcon(<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" key="p" />, 'IconShield')
export const IconPanel = createIcon([<rect x="3" y="3" width="18" height="18" rx="2" key="r" />, <path d="M3 9h18" key="p1" />, <path d="M9 21V9" key="p2" />], 'IconPanel')

// CRM / Contacts
export const IconPerson = createIcon([<path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" key="p1" />, <circle cx="12" cy="7" r="4" key="c" />], 'IconPerson')
export const IconTag = createIcon([<path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z" key="p1" />, <line x1="7" y1="7" x2="7.01" y2="7" key="l" />], 'IconTag')
export const IconMail = createIcon([<rect x="2" y="4" width="20" height="16" rx="2" key="r" />, <path d="M22 6L12 13L2 6" key="p" />], 'IconMail')
export const IconMapPin = createIcon([<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" key="p1" />, <circle cx="12" cy="10" r="3" key="c" />], 'IconMapPin')

// Status
export const IconPackage = createIcon([<path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z" key="p1" />, <polyline points="3.27 6.96 12 12.01 20.73 6.96" key="p2" />, <line x1="12" y1="22.08" x2="12" y2="12" key="l" />], 'IconPackage')

// Missing icons for Dashboard, Pagos, Plataforma
export const IconMessageCircle = createIcon([<path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8.9h.5a8.48 8.48 0 018 8v.5z" key="p" />], 'IconMessageCircle')
export const IconArrowRight = createIcon(<path d="M5 12h14M12 5l7 7-7 7" key="p" />, 'IconArrowRight')
export const IconTrendingUp = createIcon([<polyline points="23 6 13.5 15.5 8.5 10.5 1 18" key="p1" />, <polyline points="17 6 17 18 1 18" key="p2" />], 'IconTrendingUp')
export const IconActivity = createIcon([<polyline points="22 12 18 12 15 21 9 3 6 12 2 12" key="p" />], 'IconActivity')
export const IconStar = createIcon([<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 1 14.14 6.99 9.27 12 2" key="p" />], 'IconStar')
export const IconPower = createIcon([<path d="M18.36 6.64a9 9 0 11-12.73 0" key="p1" />, <line x1="12" y1="2" x2="12" y2="12" key="l" />], 'IconPower')

// Theme icons
export const IconSun = createIcon([<circle cx="12" cy="12" r="5" key="c" />, <line x1="12" y1="1" x2="12" y2="3" key="l1" />, <line x1="12" y1="21" x2="12" y2="23" key="l2" />, <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" key="l3" />, <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" key="l4" />, <line x1="1" y1="12" x2="3" y2="12" key="l5" />, <line x1="21" y1="12" x2="23" y2="12" key="l6" />, <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" key="l7" />, <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" key="l8" />], 'IconSun')
export const IconMoon = createIcon([<path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" key="p" />], 'IconMoon')
// Sistema: círculo mitad sol / mitad luna (autorral, no glifo unicode)
export const IconAuto = createIcon([
  <circle cx="12" cy="12" r="9" key="c" />,
  <path d="M12 3a9 9 0 000 18z" fill="currentColor" stroke="none" key="half" />,
  <line x1="12" y1="1" x2="12" y2="3" key="l1" />,
  <line x1="12" y1="21" x2="12" y2="23" key="l2" />,
  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" key="l3" />,
  <line x1="1" y1="12" x2="3" y2="12" key="l4" />,
  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" key="l5" />,
], 'IconAuto')

// IA / Proveedores
export const IconBrain = createIcon([
  <path d="M12 2a3 3 0 00-3 3v7a3 3 0 006 0V5a3 3 0 00-3-3z" key="p1" />,
  <path d="M12 17a3 3 0 01-3-3V9a3 3 0 016 0v5a3 3 0 01-3 3z" key="p2" />,
  <path d="M3 12h18" key="p3" />,
  <path d="M12 3v3" key="p4" />,
  <path d="M12 18v3" key="p5" />,
], 'IconBrain')

export const IconKey = createIcon([
  <path d="M15.5 3.5a2.5 2.5 0 110 5H14v11a1 1 0 01-2 0V8.5H8.5a2.5 2.5 0 110-5H10V2a1 1 0 012 0v1.5h3.5z" key="p1" />,
  <circle cx="15.5" cy="3.5" r="1.5" key="p2" />,
], 'IconKey')