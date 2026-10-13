import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const loginView = readFileSync(resolve(__dirname, '../src/views/LoginView.vue'), 'utf8')
const styleMatch = loginView.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
const style = styleMatch ? styleMatch[1] : ''

function assertContains(source, pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(`Missing: ${message}`)
  }
}

// Login side should not center vertically on mobile; it should be at the top
assertContains(style, /@media\s*\(\s*max-width:\s*768px\s*\)[\s\S]*\.login-side\s*\{[^}]*justify-content:\s*flex-start/s, 'login-side justify-content flex-start in mobile')

console.log('Login mobile no-gap assertions passed')
