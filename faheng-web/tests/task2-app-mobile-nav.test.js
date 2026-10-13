import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const appVue = readFileSync(resolve(__dirname, '../src/App.vue'), 'utf8')
const scriptMatch = appVue.match(/<script[^>]*setup[^>]*>([\s\S]*?)<\/script>/)
const styleMatch = appVue.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
const script = scriptMatch ? scriptMatch[1] : ''
const style = styleMatch ? styleMatch[1] : ''

function assertContains(source, pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(`Missing: ${message}`)
  }
}

assertContains(script, /isMobileMenuOpen\s*=\s*ref\s*\(\s*false\s*\)/, 'isMobileMenuOpen ref')
assertContains(script, /checkMobile\s*\(\s*\)\s*\{[^}]*window\.innerWidth\s*<=?\s*768/, 'window width check for 768px')
assertContains(script, /addEventListener\s*\(\s*['"]resize['"]\s*,\s*checkMobile/, 'resize listener')
assertContains(appVue, /import\s*\{\s*Menu\s*\}\s*from\s*['"]@element-plus\/icons-vue['"]/, 'Menu icon import')
assertContains(appVue, /mobile-menu-toggle/, 'mobile menu toggle element')
assertContains(appVue, /mobile-nav/, 'mobile navigation element')
assertContains(appVue, /v-show="[^"]*isMobileMenuOpen[^"]*"/, 'mobile menu show binding')
assertContains(style, /\.mobile-menu-toggle/, 'mobile menu toggle styles')
assertContains(style, /\.mobile-nav/, 'mobile navigation styles')
assertContains(style, /@media\s*\(\s*max-width:\s*768px\s*\)[\s\S]*\.top-bar/, 'top-bar media query')

console.log('Task 2 App.vue assertions passed')
