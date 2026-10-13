import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, resolve } from 'path'

const __filename = fileURLToPath(import.meta.url)
const __dirname = dirname(__filename)

const milestoneTable = readFileSync(resolve(__dirname, '../src/components/compliance/MilestoneTable.vue'), 'utf8')
const reportPanel = readFileSync(resolve(__dirname, '../src/components/review/ReportPanel.vue'), 'utf8')

function assertContains(source, pattern, message) {
  if (!pattern.test(source)) {
    throw new Error(`Missing: ${message}`)
  }
}

// MilestoneTable checks
const msStyle = milestoneTable.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
const msStyleContent = msStyle ? msStyle[1] : ''
assertContains(milestoneTable, /class="table-scroll-wrap"/, 'MilestoneTable table-scroll-wrap class')
assertContains(msStyleContent, /\.table-scroll-wrap\s*\{[^}]*overflow-x:\s*auto/s, 'MilestoneTable overflow-x auto')
assertContains(msStyleContent, /\.table-scroll-wrap\s+\.el-table\s*\{[^}]*min-width:/s, 'MilestoneTable el-table min-width')

// ReportPanel checks
const rpStyle = reportPanel.match(/<style[^>]*scoped[^>]*>([\s\S]*?)<\/style>/)
const rpStyleContent = rpStyle ? rpStyle[1] : ''
assertContains(reportPanel, /class="table-scroll-wrap"/, 'ReportPanel table-scroll-wrap class')
assertContains(rpStyleContent, /\.table-scroll-wrap\s*\{[^}]*overflow-x:\s*auto/s, 'ReportPanel overflow-x auto')
assertContains(rpStyleContent, /\.table-scroll-wrap\s+\.el-table\s*\{[^}]*min-width:/s, 'ReportPanel el-table min-width')

console.log('Task 10 table scroll assertions passed')
