// One-shot visual verification: login, capture every screen (desktop +
// mobile) and run a numeric WCAG audit. Uses the system Edge/Chrome so no
// browser download is needed. Run from admin-web with servers up.

import { chromium } from 'playwright'

const R = 'C:/Users/juand/AppData/Local/Temp/opencode/impeccable-review'
const BASE = 'http://localhost:5173'
const EMAIL = 'qa.panel.demo@gmail.com'
const PASSWORD = 'AuraQA2026!'

const results = {}
const step = async (key, fn) => {
  try {
    await fn()
    results[key] = 'ok'
  } catch (e) {
    results[key] = 'FAIL: ' + String(e).slice(0, 120)
  }
}

async function launchBrowser() {
  const attempts = [
    { channel: 'msedge', headless: true },
    { channel: 'chrome', headless: true },
    { headless: true },
  ]
  let lastError = null
  for (const options of attempts) {
    try {
      return await chromium.launch(options)
    } catch (e) {
      lastError = e
    }
  }
  throw lastError
}

const browser = await launchBrowser()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const consoleErrors = []
page.on('console', (msg) => {
  if (msg.type() === 'error') {
    consoleErrors.push(msg.text().slice(0, 200))
  }
})

const shot = (name) =>
  page.screenshot({ path: `${R}/${name}`, fullPage: true, animations: 'disabled', timeout: 60000 })

// ── Login + desktop flow ────────────────────────────────────────────────────
await step('login-desktop', async () => {
  await page.goto(`${BASE}/login`)
  await page.waitForSelector('#email', { timeout: 30000 })
  await page.waitForTimeout(800)
  await shot('login-desktop.png')
})

await step('login-do', async () => {
  await page.fill('#email', EMAIL)
  await page.fill('#password', PASSWORD)
  const responsePromise = page
    .waitForResponse((r) => r.url().includes('/auth/login'), { timeout: 20000 })
    .catch(() => null)
  await page.click('button[type="submit"]')
  const response = await responsePromise
  results['login-response'] = response ? `${response.status()}` : 'no-response'
  await page.waitForURL('**/', { timeout: 30000 })
  results['login-url-after'] = page.url()
  await page.waitForTimeout(1500)
  await shot('panel-desktop.png')
})

await step('servicios-desktop', async () => {
  await page.goto(`${BASE}/servicios`)
  await page.waitForSelector('text=Cotizador', { timeout: 30000 })
  await page.waitForTimeout(400)
  await shot('servicios-desktop.png')
})

await step('quoter-catalog-desktop', async () => {
  await page.goto(`${BASE}/servicios/quoter/catalogo`)
  await page.waitForSelector('text=Tomacorriente doble', { timeout: 30000 })
  await page.waitForTimeout(400)
  await shot('quoter-catalog-desktop.png')
})

await step('quoter-quotes-desktop', async () => {
  await page.goto(`${BASE}/servicios/quoter/cotizaciones`)
  await page.waitForSelector('text=Abrir', { timeout: 30000 })
  await page.waitForTimeout(400)
  await shot('quoter-quotes-desktop.png')
})

await step('quote-detail-desktop', async () => {
  await page.click('text=Abrir')
  await page.waitForSelector('text=Cotización #', { timeout: 30000 })
  await page.waitForTimeout(800)
  await shot('quote-detail-desktop.png')
})

await step('clientes-desktop', async () => {
  await page.goto(`${BASE}/clientes`)
  await page.waitForSelector('text=María', { timeout: 30000 })
  await page.waitForTimeout(400)
  await shot('clientes-desktop.png')
})

// ── Mobile flow (session persists via localStorage after the AuthContext fix) ─
await step('panel-mobile', async () => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto(`${BASE}/`)
  await page.waitForTimeout(1500)
  await shot('panel-mobile.png')
})

await step('clientes-mobile', async () => {
  await page.goto(`${BASE}/clientes`)
  await page.waitForSelector('text=María', { timeout: 30000 })
  await page.waitForTimeout(400)
  await shot('clientes-mobile.png')
})

// ── Numeric WCAG audit on the live CSS ─────────────────────────────────────
let audit = null
await step('audit', async () => {
  audit = await page.evaluate(() => {
    const lum = (rgb) => {
      const [r, g, b] = rgb
        .match(/[\d.]+/g)
        .slice(0, 3)
        .map(Number)
      const f = (c) => {
        const s = c / 255
        return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
      }
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    }
    const ratio = (a, b) => {
      const [l1, l2] = [lum(a), lum(b)].sort((x, y) => y - x)
      return (l1 + 0.05) / (l2 + 0.05)
    }
    const bgOf = (el) => {
      let current = el
      while (current) {
        const bg = getComputedStyle(current).backgroundColor
        if (bg && bg !== 'rgba(0, 0, 0, 0)') {
          return bg
        }
        current = current.parentElement
      }
      return 'rgb(244, 241, 233)'
    }
    const check = (selector, min, label) => {
      const el = document.querySelector(selector)
      if (!el) {
        return { label, status: 'MISSING', selector }
      }
      const cs = getComputedStyle(el)
      const value = ratio(cs.color, bgOf(el))
      return {
        label,
        value: Number(value.toFixed(2)),
        min,
        status: value >= min ? 'pass' : 'fail',
        color: cs.color,
        bg: bgOf(el),
      }
    }
    // Probe: fabricate the exact state classes and measure computed styles
    const probe = (classes, parentClasses, label, min) => {
      const parent = document.createElement('div')
      parent.className = parentClasses
      parent.style.position = 'fixed'
      parent.style.top = '-9999px'
      const el = document.createElement('span')
      el.className = classes
      el.textContent = 'x'
      parent.appendChild(el)
      document.body.appendChild(parent)
      const cs = getComputedStyle(el)
      const value = ratio(cs.color, bgOf(el))
      const result = {
        label,
        value: Number(value.toFixed(2)),
        min,
        status: value >= min ? 'pass' : 'fail',
        color: cs.color,
        bg: bgOf(el),
      }
      parent.remove()
      return result
    }
    const checks = [
      check('h1', 3, 'H1 título (EB Garamond)'),
      check('.plate-label', 4.5, 'Etiqueta de papelería'),
      check('table td', 4.5, 'Celdas de tabla'),
      check('input', 4.5, 'Texto de input'),
      probe('px-2 py-1 text-xs font-medium rounded-full bg-brass-wash text-brass-ink', '', 'Badge Vencida (brass-ink sobre brass-wash)', 4.5),
      probe('px-2 py-1 text-xs font-medium rounded-full bg-linen-100 text-linen-600', '', 'Badge Borrador', 4.5),
      probe('text-sm font-medium text-brass-bright', 'bg-pine bg-white/10 h-10 w-40', 'Nav activa escritorio (brass-bright sobre pino+blanco/10)', 4.5),
      probe('text-xs font-medium text-lacre-tint', 'bg-pine h-10 w-40', 'Cerrar sesión (lacre-tint sobre pino)', 4.5),
      probe('text-sm font-medium text-brass-bright', 'bg-pine h-11 w-40', 'Pestaña móvil activa (brass-bright sobre pino)', 4.5),
    ]
    const tabularEl = document.querySelector('.tabular')
    const tabular = tabularEl
      ? getComputedStyle(tabularEl).fontVariantNumeric
      : 'none'
    const rail = document.querySelector('nav .bg-brass')
    const h1el = document.querySelector('h1')
    return {
      checks,
      tabularNumeric: tabular,
      brassRailPresent: Boolean(rail),
      h1Font: h1el ? getComputedStyle(h1el).fontFamily.slice(0, 60) : null,
      bodyFont: getComputedStyle(document.body).fontFamily.slice(0, 60),
      bodyBg: getComputedStyle(document.body).backgroundColor,
    }
  })
})

await browser.close()
console.log(JSON.stringify({ results, audit, consoleErrors }, null, 2))
