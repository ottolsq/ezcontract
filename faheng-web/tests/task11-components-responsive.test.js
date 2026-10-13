import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const components = {
  ContractCards: '../src/components/compliance/ContractCards.vue',
  UploadZone: '../src/components/review/UploadZone.vue',
  UploadPanel: '../src/components/compliance/UploadPanel.vue',
  LoadingIndicator: '../src/components/LoadingIndicator.vue',
  NotificationBell: '../src/components/NotificationBell.vue',
  StatsStrip: '../src/components/review/StatsStrip.vue',
  RiskListPane: '../src/components/review/RiskListPane.vue',
}

function getStyle(path) {
  const content = readFileSync(resolve(__dirname, path), 'utf8')
  const match = content.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
  return match ? match[1] : ''
}

function assertContains(source, pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(`Missing: ${message}`)
  }
}

// ContractCards
const contractCards = readFileSync(resolve(__dirname, components.ContractCards), 'utf8')
assertContains(contractCards, /:width\s*=\s*["']dialogWidth["']/, 'ContractCards dialog width binding')
assertContains(contractCards, /const\s+dialogWidth\s*=\s*computed/, 'ContractCards dialogWidth computed')

// UploadZone / UploadPanel
const uploadZoneStyle = getStyle(components.UploadZone)
const uploadPanelStyle = getStyle(components.UploadPanel)
assertContains(uploadZoneStyle, /@media\s*\(\s*max-width:\s*768px\s*\)/, 'UploadZone 768px media query')
assertContains(uploadPanelStyle, /@media\s*\(\s*max-width:\s*768px\s*\)/, 'UploadPanel 768px media query')

// LoadingIndicator
const loadingIndicatorStyle = getStyle(components.LoadingIndicator)
assertContains(loadingIndicatorStyle, /min\(\s*400px\s*,\s*calc\(\s*100%\s+-\s*32px\s*\)\)/, 'LoadingIndicator responsive width')

// NotificationBell
const notificationBell = readFileSync(resolve(__dirname, components.NotificationBell), 'utf8')
assertContains(notificationBell, /:width\s*=\s*["']popoverWidth["']/, 'NotificationBell popover width binding')
assertContains(notificationBell, /const\s+popoverWidth\s*=\s*computed/, 'NotificationBell popoverWidth computed')

// StatsStrip
const statsStripStyle = getStyle(components.StatsStrip)
assertContains(statsStripStyle, /@media\s*\(\s*max-width:\s*768px\s*\)/, 'StatsStrip 768px media query')

// RiskListPane
const riskListPaneStyle = getStyle(components.RiskListPane)
assertContains(riskListPaneStyle, /@media\s*\(\s*max-width:\s*768px\s*\)/, 'RiskListPane 768px media query')

console.log('Task 11 component responsive assertions passed')
