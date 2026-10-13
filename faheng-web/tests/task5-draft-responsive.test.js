import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const draftView = readFileSync(resolve(__dirname, '../src/views/DraftView.vue'), 'utf8')
const styleMatch = draftView.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
const style = styleMatch ? styleMatch[1] : ''

function assertContains(source, pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(`Missing: ${message}`)
  }
}

assertContains(style, /@media\s*\(\s*max-width:\s*768px\s*\)/, '768px media query')
assertContains(style, /\.page-head\s*\{[^}]*flex-wrap:\s*wrap/s, 'page-head flex-wrap wrap')
assertContains(style, /\.head-actions\s*\{[^}]*flex-wrap:\s*wrap/s, 'head-actions flex-wrap wrap')
assertContains(style, /\.revise-row\s*\{[^}]*flex-direction:\s*column/s, 'revise-row column on mobile')
assertContains(style, /\.revise-row\s+\.el-input[^\{]*\{[^}]*width:\s*100%/s, 'revise input full width on mobile')

console.log('Task 5 DraftView responsive assertions passed')
