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

// brand-side should be visible and centered on mobile
assertContains(style, /@media\s*\(\s*max-width:\s*768px\s*\)[\s\S]*\.brand-side\s*\{[^}]*display:\s*flex/s, 'brand-side visible flex in 768px')
assertContains(style, /\.brand-side\s*\{[^}]*text-align:\s*center/s, 'brand-side text-align center')
assertContains(style, /\.brand-hero\s+h1\s*\{[^}]*font-size:\s*22px/s, 'brand-hero h1 has mobile font-size')
assertContains(style, /\.brand-lead\s*\{[^}]*font-size:\s*13px/s, 'brand-lead has mobile font-size')

console.log('Login mobile brand assertions passed')
