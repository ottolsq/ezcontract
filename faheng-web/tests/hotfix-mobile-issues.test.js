import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const appVue = readFileSync(resolve(__dirname, '../src/App.vue'), 'utf8')
const indexCss = readFileSync(resolve(__dirname, '../src/styles/index.css'), 'utf8')

function assertContains(source, pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(`Missing: ${message}`)
  }
}

// 1. 首页/主内容区在移动端可滚动
assertContains(appVue, /@media\s*\(\s*max-width:\s*768px\s*\)[\s\S]*\.app-main\s*\{[^}]*overflow(-[xy])?:\s*auto/s, 'app-main overflow auto on mobile')

// 2. nav 在移动端通过 desktop-only 隐藏
assertContains(appVue, /class="nav\s+desktop-only"/, 'nav uses desktop-only class')
assertContains(indexCss, /\.desktop-only\s*\{[^}]*display:\s*none\s*!important/s, 'desktop-only display none !important')

// 3. 点击遮罩层关闭菜单
assertContains(appVue, /mobile-nav-overlay/, 'mobile nav overlay')
assertContains(appVue, /isMobileMenuOpen\s*=\s*false/, 'overlay click closes menu')

// 4. brand 移动端截断
assertContains(appVue, /class="brand-short\s+mobile-only"/, 'brand-short mobile-only element')
assertContains(appVue, /class="brand-full\s+desktop-only"/, 'brand-full desktop-only element')

// 5. desktop-only 在移动端强制隐藏
assertContains(indexCss, /\.desktop-only\s*\{[^}]*display:\s*none\s*!important/s, 'desktop-only display none !important')

console.log('Hotfix assertions passed')
