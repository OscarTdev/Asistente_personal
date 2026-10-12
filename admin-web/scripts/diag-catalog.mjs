// Diagnostic: what happens on /catalog in the browser (network + errors + text)?

import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'

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

const apiLog = []
page.on('response', (r) => {
  if (r.url().includes('/api/')) {
    apiLog.push(`${r.status()} ${r.request().method()} ${r.url().replace('http://localhost:5173', '')}`)
  }
})
page.on('pageerror', (e) => apiLog.push('PAGEERROR: ' + String(e).slice(0, 200)))

// Login first (through the UI)
await page.goto(`${BASE}/login`)
await page.waitForSelector('#email', { timeout: 30000 })
await page.fill('#email', 'qa.panel.demo@gmail.com')
await page.fill('#password', 'AuraQA2026!')
await page.click('button[type="submit"]')
await page.waitForURL('**/', { timeout: 30000 })
apiLog.push('LOGIN OK -> ' + page.url())

// Now the catalog page with generous settle time
await page.goto(`${BASE}/catalog`)
await page.waitForTimeout(10000)

const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 600))
const hasTable = await page.evaluate(() => Boolean(document.querySelector('table')))
const hasErrata = await page.evaluate(() => document.body.innerText.includes('Errata'))
const hasSkeleton = await page.evaluate(() => Boolean(document.querySelector('.skel')))

console.log(JSON.stringify({ apiLog, hasTable, hasErrata, hasSkeleton, bodyText }, null, 2))
await browser.close()
