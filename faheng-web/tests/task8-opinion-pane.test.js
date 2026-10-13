import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const opinionPane = readFileSync(resolve(__dirname, '../src/components/review/OpinionPane.vue'), 'utf8')
const styleMatch = opinionPane.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
const style = styleMatch ? styleMatch[1] : ''

function assertContains(source, pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(`Missing: ${message}`)
  }
}

assertContains(style, /@media\s*\(\s*max-width:\s*768px\s*\)/, '768px media query')
assertContains(style, /\.decision-actions\s*\{[^}]*grid-template-columns:\s*1fr/s, 'decision-actions single column on mobile')
assertContains(style, /\.decision-actions\s+\.el-button/s, 'decision-actions button mobile styles')

console.log('Task 8 OpinionPane responsive assertions passed')
