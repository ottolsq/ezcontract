import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const homeView = readFileSync(resolve(__dirname, '../src/views/HomeView.vue'), 'utf8')
const styleMatch = homeView.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
const style = styleMatch ? styleMatch[1] : ''

function assertContains(source, pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(`Missing: ${message}`)
  }
}

assertContains(style, /@media\s*\(\s*max-width:\s*768px\s*\)/, '768px media query')
assertContains(style, /@media\s*\(\s*max-width:\s*480px\s*\)/, '480px media query')
assertContains(style, /\.home\s*\{[^}]*padding:\s*16px/s, 'home padding 16px on mobile')
assertContains(style, /\.cards\s*\{[^}]*grid-template-columns:\s*1fr/s, 'cards single column on mobile')
assertContains(style, /\.home\s+h1\s*\{[^}]*font-size:\s*22px/s, 'home h1 font-size 22px on mobile')

console.log('Task 4 HomeView responsive assertions passed')
