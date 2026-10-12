// Minimal login diagnostic: what exactly happens on submit?

import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'

async function launchBrowser() {
  for (const options of [{ channel: 'msedge', headless: true }, { channel: 'chrome', headless: true }, { headless: true }]) {
    try {
      return await chromium.launch(options)
    } catch (e) {
      // try next
    }
  }
  throw new Error('no browser available')
}

const browser = await launchBrowser()
const page = await browser.newPage()

const apiRequests = []
const pageErrors = []
const consoleMessages = []
page.on('request', (r) => {
  if (r.url().includes('/api/')) {
    apiRequests.push(r.method() + ' ' + r.url())
  }
})
page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 300)))
page.on('console', (m) => consoleMessages.push(m.type() + ': ' + m.text().slice(0, 200)))

await page.goto(`${BASE}/login`)
await page.waitForSelector('#email', { timeout: 30000 })
await page.waitForTimeout(500)

await page.fill('#email', 'qa.panel.demo@gmail.com')
await page.fill('#password', 'AuraQA2026!')

const before = await page.evaluate(() => {
  const email = document.querySelector('#email')
  const password = document.querySelector('#password')
  const form = email?.closest('form')
  return {
    emailValue: email?.value ?? null,
    passwordValue: password?.value ?? null,
    formValidity: form ? form.checkValidity() : null,
    emailValidity: email?.validationMessage ?? null,
    buttonExists: Boolean(document.querySelector('button[type="submit"]')),
    buttonDisabled: document.querySelector('button[type="submit"]')?.disabled ?? null,
  }
})

// Submit with Enter (avoids any click-target issue)
await page.press('#password', 'Enter')
await page.waitForTimeout(4000)

const after = {
  url: page.url(),
  errataVisible: await page.evaluate(() => document.body.innerText.includes('Errata')),
}

console.log(JSON.stringify({ before, after, apiRequests, pageErrors, consoleMessages }, null, 2))
await browser.close()
