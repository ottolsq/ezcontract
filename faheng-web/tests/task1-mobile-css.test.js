import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const css = readFileSync(resolve(__dirname, '../src/styles/index.css'), 'utf8')

function assertContains(pattern, message) {
  if (!pattern.test(css)) {
    throw new Error(`Missing: ${message}`)
  }
}

// Extract the contents of a media query block for focused checks
const mediaBlock = css.match(/@media\s*\(\s*max-width:\s*768px\s*\)\s*\{([\s\S]*?)\n\}/)
const mediaContent = mediaBlock ? mediaBlock[1] : ''

// Global responsive variables and utility classes
assertContains(/--mobile-breakpoint:\s*768px/, 'CSS variable --mobile-breakpoint')
assertContains(/--small-mobile-breakpoint:\s*480px/, 'CSS variable --small-mobile-breakpoint')
assertContains(/\.mobile-only\s*\{\s*display:\s*none;?\s*\}/s, '.mobile-only hides by default')
assertContains(/\.mobile-only\s*\{\s*display:\s*initial;?\s*\}/s, '.mobile-only shows below 768px')
assertContains(/\.desktop-only\s*\{\s*display:\s*none;?\s*\}/s, '.desktop-only hides below 768px')

// Element Plus dialog mobile override
assertContains(/@media\s*\(\s*max-width:\s*768px\s*\)/, 'media query for 768px')
assertContains(/\.el-dialog\s*\{[^}]*width:\s*calc\(100vw\s+-\s+32px\)/s, '.el-dialog responsive width')
assertContains(/\.el-message-box\s*\{[^}]*width:\s*calc\(100vw\s+-\s+32px\)/s, '.el-message-box responsive width')

console.log('Task 1 CSS assertions passed')
