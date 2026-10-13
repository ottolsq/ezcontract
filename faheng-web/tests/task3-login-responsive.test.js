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

assertContains(style, /@media\s*\(\s*max-width:\s*768px\s*\)/, '768px media query')
assertContains(style, /@media\s*\(\s*max-width:\s*480px\s*\)/, '480px media query')
assertContains(style, /\.login-card\s*\{[^}]*max-width:\s*420px/s, 'login-card max-width 420px in mobile')
assertContains(style, /\.captcha-row\s*\{[^}]*flex-wrap:\s*wrap/s, 'captcha-row flex-wrap wrap')
assertContains(style, /\.login-actions\s*\{[^}]*flex-direction:\s*column/s, 'login-actions column on small screens')

console.log('Task 3 LoginView responsive assertions passed')
