# Plan de Mejoras - Frontend Aura

## 1. Problemas de UI/UX Actuales
- [ ] **Transparencia en botones/elementos**: Las variables CSS de shadcn/ui no están bien mapeadas
- [ ] **Tamaño de fuente grande**: 14px base, elementos más grandes de lo necesario
- [ ] **Falta modo noche (dark mode)**: Solo está definido en CSS pero no hay toggle en UI
- [ ] **Poca interactividad**: Falta feedback visual, animaciones, estados de carga
- [ ] **Finanzas no muestra datos**: Verificar que el módulo esté habilitado y la API funcione

## 2. Nuevas Funcionalidades
- [ ] **Búsqueda en internet**: Integración con API de búsqueda (ej. Tavily, SerpAPI, o DuckDuckGo HTML scraping)
- [ ] **Soporte multimedia**:
  - Subida de archivos (audio, imagen, documento)
  - STT (Speech-to-Text) para audio → texto (ya existe Groq Whisper)
  - TTS (Text-to-Speech) para respuesta en audio
  - Visualización de imágenes en chat
- [ ] **Mejoras en el chat del asistente**: Burbujas de chat, indicador de escritura, timestamps

## 3. Implementación Detallada

### 3.1 Fix CSS/Theme
- Completar mapeo de variables CSS para shadcn/ui (light + dark)
- Reducir font-size base a 13px, headings más compactos
- Agregar clase `.dark` al html basado en preferencia del usuario + localStorage
- Toggle de tema en topbar (icono sol/luna)

### 3.2 Dark Mode
- Persistir preferencia en localStorage
- Respetar `prefers-color-scheme` por defecto
- Transición suave entre temas

### 3.3 Búsqueda en Internet
- Nueva intención `web_search` en el backend
- Endpoint `/api/v1/web-search` 
- UI: botón "Buscar en web" o detección automática

### 3.4 Multimedia
- Backend: endpoints para upload de archivos a Evolution API
- Frontend: zona de drop/click para archivos en chat
- STT: usar Groq Whisper (ya configurado en .env)
- TTS: Edge TTS (gratis, voz es-CO-ElenaNeural) o ElevenLabs
- Reproductor de audio en burbujas de chat

### 3.5 Finanzas
- Verificar que `personal_finance` esté habilitado en el tenant
- Mejorar UI de ServiceDataPage para gastos (totales por categoría, gráfico)
- Agregar botón "Registrar gasto" manual

### 3.6 Interactividad General
- Hover states más pronunciados
- Loading skeletons en todas las páginas
- Toast notifications para acciones
- Confirmaciones antes de acciones destructivas
- Keyboard shortcuts (Cmd+K para búsqueda, etc.)

## 4. Archivos a Modificar

### CSS/Theme
- `admin-web/src/index.css` - Variables completas, dark mode, tipografía
- `admin-web/tailwind.config.ts` - Configuración de dark mode class

### Layout/Shell
- `admin-web/src/components/layout/AppLayout.tsx` - Toggle dark mode, búsqueda global
- `admin-web/src/auth/AuthContext.tsx` - Estado de tema

### Páginas
- `admin-web/src/pages/ServiceDataPage.tsx` - Mejorar finanzas (gráficos, totales)
- `admin-web/src/pages/ClientesPage.tsx` - Chat con multimedia
- `admin-web/src/pages/DashboardPage.tsx` - KPIs interactivos

### Componentes
- `admin-web/src/components/ui/button.tsx` - Variantes mejoradas
- `admin-web/src/components/ui/input.tsx` - Con zona de drop
- Nuevo: `admin-web/src/components/ui/audio-player.tsx`
- Nuevo: `admin-web/src/components/ui/file-upload.tsx`
- Nuevo: `admin-web/src/components/chat/ChatBubble.tsx`
- Nuevo: `admin-web/src/components/chat/ChatInput.tsx`

### Backend (Nuevos endpoints)
- `backend/app/api/v1/web_search.py` - Búsqueda en internet
- `backend/app/api/v1/media.py` - Upload/STT/TTS
- Actualizar `orchestrator.py` - Nueva intención `web_search`

## 5. Prioridad
1. **Crítico**: Fix transparencia, font-size, dark mode toggle
2. **Alto**: Finanzas funcionando, multimedia básico (audio)
3. **Medio**: Búsqueda internet, TTS respuesta
4. **Nice to have**: Gráficos en finanzas, shortcuts keyboard