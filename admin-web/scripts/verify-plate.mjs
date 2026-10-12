// Quick verify: plate-label contrast after the linen-600 fix.

import { chromium } from 'playwright'

async function launchBrowser() {
  for (const options of [{ channel: 'msedge', headless: true }, { channel: 'chrome', headless: true }, { headless: true }]) {
    try {
      return await chromium.launch(options)
    } catch (e) {}
  }
  throw new Error('no browser available')
}

const browser = await launchBrowser()
const page = await browser.newPage()
await page.goto('http://localhost:5173/login')
await page.waitForSelector('#email', { timeout: 30000 })
await page.fill('#email', 'qa.panel.demo@gmail.com')
await page.fill('#password', 'AuraQA2026!')
await page.click('button[type="submit"]')
await page.waitForURL('**/', { timeout: 30000 })
await page.goto('http://localhost:5173/modules')
await page.waitForSelector('text=Cotizador', { timeout: 30000 })
await page.waitForTimeout(600)

const result = await page.evaluate(() => {
  const lum = (rgb) => {
    const [r, g, b] = rgb.match(/[\d.]+/g).slice(0, 3).map(Number)
    const f = (c) => {
      const s = c / 255
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
  }
  const el = document.querySelector('.plate-label')
  const cs = getComputedStyle(el)
  let bgEl = el
  let bg = 'rgba(0, 0, 0, 0)'
  while (bgEl) {
    bg = getComputedStyle(bgEl).backgroundColor
    if (bg && bg !== 'rgba(0, 0, 0, 0)') break
    bgEl = bgEl.parentElement
  }
  const ratio = (lum(cs.color) + 0.05) / (lum(bg) + 0.05)
  const ratioCeil = ratio < 1 ? 1 / ratio : ratio
  return { color: cs.color, bg, ratio: Number(ratioCeil.toFixed(2)), pass: ratioCeil >= 4.5 }
})
console.log(JSON.stringify(result))
await browser.close()
