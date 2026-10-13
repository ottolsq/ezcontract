import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const complianceView = readFileSync(resolve(__dirname, '../src/views/ComplianceView.vue'), 'utf8')
const styleMatch = complianceView.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
const style = styleMatch ? styleMatch[1] : ''

function assertContains(source, pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(`Missing: ${message}`)
  }
}

assertContains(style, /@media\s*\(\s*max-width:\s*768px\s*\)/, '768px media query')
assertContains(style, /\.page-head\s*\{[^}]*flex-wrap:\s*wrap/s, 'page-head flex-wrap wrap')
assertContains(style, /\.stats-strip\s*\{[^}]*flex-wrap:\s*wrap/s, 'stats-strip flex-wrap wrap')
assertContains(style, /\.contract-head\s*\{[^}]*flex-direction:\s*column/s, 'contract-head column on mobile')
assertContains(style, /\.contract-info\s*\{[^}]*width:\s*100%/s, 'contract-info width 100% on mobile')

console.log('Task 9 ComplianceView responsive assertions passed')
