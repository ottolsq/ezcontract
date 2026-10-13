import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const reviewView = readFileSync(resolve(__dirname, '../src/views/ReviewView.vue'), 'utf8')
const scriptMatch = reviewView.match(/<script[^>]*setup[^>]*>([\s\S]*?)<\/script>/)
const templateMatch = reviewView.match(/<template>([\s\S]*?)<\/template>/)
const styleMatch = reviewView.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
const script = scriptMatch ? scriptMatch[1] : ''
const template = templateMatch ? templateMatch[1] : ''
const style = styleMatch ? styleMatch[1] : ''

function assertContains(source, pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(`Missing: ${message}`)
  }
}

assertContains(script, /isMobileLayout\s*=\s*ref\s*\(\s*false\s*\)/, 'isMobileLayout ref')
assertContains(script, /window\.innerWidth\s*<=?\s*768/, 'window width check for 768px')
assertContains(script, /activeMobileTab\s*=\s*ref\s*\(\s*['"]risk['"]\s*\)/, 'activeMobileTab ref with risk default')
assertContains(template, /v-if="!isMobileLayout"/, 'desktop workspace guard')
assertContains(template, /v-else[\s\S]*el-tabs/, 'mobile tabs block')
assertContains(template, /el-tab-pane\s+label="风险"/, 'risk tab pane')
assertContains(template, /el-tab-pane\s+label="合同"/, 'contract tab pane')
assertContains(template, /el-tab-pane\s+label="意见"/, 'opinion tab pane')
assertContains(style, /@media\s*\(\s*max-width:\s*768px\s*\)/, '768px media query')

console.log('Task 7 ReviewView tab assertions passed')
