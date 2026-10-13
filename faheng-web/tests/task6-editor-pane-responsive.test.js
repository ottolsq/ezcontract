import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const richEditor = readFileSync(resolve(__dirname, '../src/components/draft/RichEditor.vue'), 'utf8')
const contractPane = readFileSync(resolve(__dirname, '../src/components/review/ContractPane.vue'), 'utf8')

function assertContains(source, pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(`Missing: ${message}`)
  }
}

// RichEditor checks
const richStyle = richEditor.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
const richStyleContent = richStyle ? richStyle[1] : ''
assertContains(richStyleContent, /@media\s*\(\s*max-width:\s*768px\s*\)/, 'RichEditor 768px media query')
assertContains(richStyleContent, /\.docx-page\s*\{[^}]*max-width:\s*100%/s, 'docx-page max-width 100% on mobile')
assertContains(richStyleContent, /\.docx-page\s*\{[^}]*padding:\s*16px/s, 'docx-page padding 16px on mobile')

// ContractPane checks
const paneStyle = contractPane.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
const paneStyleContent = paneStyle ? paneStyle[1] : ''
assertContains(paneStyleContent, /@media\s*\(\s*max-width:\s*768px\s*\)/, 'ContractPane 768px media query')
assertContains(paneStyleContent, /\.paper\s*\{[^}]*max-width:\s*100%/s, 'paper max-width 100% on mobile')

console.log('Task 6 RichEditor/ContractPane responsive assertions passed')
