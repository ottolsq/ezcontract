# 移动端响应式适配实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 ezContract Web 应用在 320px–768px 手机视口下正常可用，修复文字竖排、窗口溢出、表格截断等核心问题。

**Architecture:** 在现有 Vue 3 + Element Plus + scoped CSS 架构上，通过全局响应式断点、Element Plus 组件尺寸自适应、关键组件（顶部栏、审查三栏、A4 编辑器）的移动端重构，实现渐进式适配；以 768px 和 480px 为主要断点，保持桌面端不变。

**Tech Stack:** Vue 3, Element Plus, Vite, scoped CSS / CSS media queries

**Spec:** 本计划基于移动端适配审计报告：字体纵向排列、弹窗/窗口显示不全、顶部导航挤压、表格/编辑器溢出等问题。

## Global Constraints

- 不得引入 Tailwind / Bootstrap / SCSS / CSS-in-JS，沿用现有 scoped CSS + 全局 CSS 方案。
- 所有新增 CSS 必须通过 `@media` 媒体查询保护，桌面端样式不得改变。
- 断点统一使用 `768px`（平板/大手机）和 `480px`（小手机）两处；已有 `900px`/`1100px` 断点保持不变。
- Element Plus 组件优先使用原生响应式 props（如 `:width`、`fit`）而非覆盖内部样式。
- 保持中文文案不变，不修改业务逻辑和接口调用。
- 每个 Task 结束时在 Chrome DevTools 的 375px / 768px 视口下验证无横向滚动条。

## Review Focus

- 在 320px 宽视口下打开任意弹窗，不应出现横向滚动或贴边。
- 在 375px 宽视口下打开审查页，三栏应以 Tab 形式正常切换，合同正文可完整阅读。
- 在 480px 宽视口下打开起草页，修订输入框与按钮不应被截断。
- 在 768px 宽视口下打开履约页，统计卡片与表格不应溢出。
- 在桌面端（>1024px）下，所有页面外观和交互必须与适配前一致。

---

## File Structure

- `faheng-web/src/styles/index.css` — 全局响应式基础变量与 `.mobile-only`/`.desktop-only` 辅助类。
- `faheng-web/src/App.vue` — 顶部导航移动端汉堡菜单与响应式布局。
- `faheng-web/src/views/LoginView.vue` — 登录页在 <=768px 与 <=480px 下的单列优化。
- `faheng-web/src/views/HomeView.vue` — 首页卡片与容器响应式。
- `faheng-web/src/views/DraftView.vue` — 起草页标题区、表单、修订行、A4 编辑器响应式。
- `faheng-web/src/views/ReviewView.vue` — 审查页三栏变 Tab/抽屉移动端体验。
- `faheng-web/src/views/ComplianceView.vue` — 履约页统计、卡片、表格响应式。
- `faheng-web/src/components/RichEditor.vue` — 工具栏与 A4 编辑区缩放。
- `faheng-web/src/components/ContractPane.vue` — 合同预览区宽度与 padding 响应式。
- `faheng-web/src/components/OpinionPane.vue` — 决策按钮在小屏下换行。
- `faheng-web/src/components/MilestoneTable.vue` — 表格横向滚动容器。
- `faheng-web/src/components/ReportPanel.vue` — 统计表格响应式。
- `faheng-web/src/components/ContractCards.vue` — 弹窗宽度与卡片数量响应式。
- `faheng-web/src/components/UploadZone.vue` / `UploadPanel.vue` — 上传区宽度响应式。
- `faheng-web/src/components/LoadingIndicator.vue` — 进度条宽度响应式。
- `faheng-web/src/components/NotificationBell.vue` — 通知面板宽度响应式。
- `faheng-web/src/components/StatsStrip.vue` — 统计条布局响应式。
- `faheng-web/src/components/RiskListPane.vue` — 风险清单过滤按钮响应式。

---

### Task 1: 全局响应式基础与 Element Plus 弹窗默认适配

**Files:**
- Modify: `faheng-web/src/styles/index.css`

**Interfaces:**
- Produces: CSS 自定义属性 `--mobile-breakpoint: 768px`, `--small-mobile-breakpoint: 480px`；工具类 `.mobile-only`, `.desktop-only`。

- [ ] **Step 1: 添加全局响应式变量与辅助类**

在 `index.css` 顶部 `:root` 附近新增：
```css
:root {
  --mobile-breakpoint: 768px;
  --small-mobile-breakpoint: 480px;
}

.mobile-only { display: none; }
@media (max-width: 768px) {
  .mobile-only { display: initial; }
  .desktop-only { display: none; }
}
```

- [ ] **Step 2: 覆盖 Element Plus 弹窗默认最大宽度**

在 `index.css` 末尾新增：
```css
@media (max-width: 768px) {
  .el-dialog {
    width: calc(100vw - 32px) !important;
    max-width: 100vw;
    margin: 16px auto !important;
  }
  .el-message-box {
    width: calc(100vw - 32px) !important;
    max-width: 100vw;
  }
}
```

- [ ] **Step 3: 验证桌面端样式未变化**

Run: `cd /home/otto/ezContract/faheng-web && npm run build`（或 `npm run dev` 后在 1200px 视口下检查首页/登录页）。
Expected: 构建通过，桌面端布局无可见变化。

- [ ] **Step 4: 验证 375px 下弹窗不溢出**

在 DevTools 375px 视口打开任意 `el-dialog`，确认左右 margin 至少 16px。
Expected: 弹窗宽度 = `100vw - 32px`，无横向滚动。

- [ ] **Step 5: Commit**

```bash
git add faheng-web/src/styles/index.css
git commit -m "feat: 添加全局响应式断点与弹窗移动端最大宽度"
```

---

### Task 2: 顶部导航栏移动端汉堡菜单

**Files:**
- Modify: `faheng-web/src/App.vue`

**Interfaces:**
- Consumes: 全局 `.mobile-only` / `.desktop-only` 类（Task 1）。
- Produces: `isMobileMenuOpen` ref；移动端汉堡图标与下拉菜单 DOM。

- [ ] **Step 1: 在 `<script setup>` 中新增菜单状态与窗口监听**

新增：
```js
import { ref, onMounted, onUnmounted } from 'vue'

const isMobileMenuOpen = ref(false)
const isMobile = ref(false)

function checkMobile() {
  isMobile.value = window.innerWidth <= 768
  if (!isMobile.value) isMobileMenuOpen.value = false
}

onMounted(() => { checkMobile(); window.addEventListener('resize', checkMobile) })
onUnmounted(() => { window.removeEventListener('resize', checkMobile) })
```

- [ ] **Step 2: 修改顶部栏模板**

将 `top-bar` 中的 `nav` 区域改为：
```vue
<nav class="desktop-only">
  <!-- 原有 router-link -->
</nav>
<div class="mobile-menu-toggle mobile-only" @click="isMobileMenuOpen = !isMobileMenuOpen">
  <el-icon><Menu /></el-icon>
</div>
<transition name="slide">
  <nav v-show="isMobileMenuOpen" class="mobile-nav mobile-only">
    <!-- 与桌面端相同的 router-link -->
  </nav>
</transition>
```
需要 import `Menu` from `@element-plus/icons-vue` 并在 `components` 中注册（若 App.vue 未自动导入图标）。

- [ ] **Step 3: 添加/修改 scoped CSS**

在 `<style scoped>` 末尾追加：
```css
.mobile-menu-toggle { display: none; cursor: pointer; font-size: 22px; padding: 8px; }
.mobile-nav {
  position: absolute;
  top: 60px;
  left: 0;
  right: 0;
  background: #fff;
  box-shadow: 0 4px 12px rgba(0,0,0,0.1);
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  z-index: 100;
}
.mobile-nav a { padding: 8px 0; border-bottom: 1px solid #eee; }
@media (max-width: 768px) {
  .top-bar { flex-wrap: wrap; padding: 0 12px; }
  .mobile-menu-toggle { display: flex; align-items: center; }
}
```

- [ ] **Step 4: 验证**

Run: `npm run dev`，在 375px / 768px / 1200px 三种视口下访问首页。
Expected:
- 1200px：原样显示全部导航链接。
- 768px：导航链接收起，出现汉堡菜单，点击展开下拉导航。
- 375px：同 768px，菜单项可点击且不溢出。

- [ ] **Step 5: Commit**

```bash
git add faheng-web/src/App.vue
git commit -m "feat: 顶部导航添加移动端汉堡菜单"
```

---

### Task 3: 登录页响应式优化

**Files:**
- Modify: `faheng-web/src/views/LoginView.vue`

**Interfaces:**
- Produces: 登录卡片在 <=768px 与 <=480px 下的单列、全宽样式。

- [ ] **Step 1: 将现有 900px 媒体查询扩展并新增 480px 断点**

找到现有 `@media (max-width: 900px)` 区域，保留并扩展为：
```css
@media (max-width: 900px) {
  .login-page { grid-template-columns: 1fr; }
  .brand-section { display: none; }
}
@media (max-width: 768px) {
  .login-card { width: 100%; max-width: 420px; padding: 32px 24px; margin: 0 auto; }
  .captcha-row { flex-wrap: wrap; gap: 12px; }
  .captcha-row canvas { width: 100px !important; height: 38px !important; }
}
@media (max-width: 480px) {
  .login-card { padding: 24px 16px; }
  .login-card .el-form-item__label { font-size: 14px; }
  .login-actions { flex-direction: column; gap: 12px; }
  .login-actions button { width: 100%; }
}
```

- [ ] **Step 2: 验证**

在 375px / 768px / 1200px 下访问 `/login`。
Expected:
- 375px：登录卡片占满宽度，内边距 16px，验证码行不溢出，底部按钮纵向排列。
- 768px：单列，卡片居中，左右留白舒适。
- 1200px：保持桌面双列布局。

- [ ] **Step 3: Commit**

```bash
git add faheng-web/src/views/LoginView.vue
git commit -m "feat: 登录页适配 768px/480px 视口"
```

---

### Task 4: 首页（HomeView）卡片与容器响应式

**Files:**
- Modify: `faheng-web/src/views/HomeView.vue`

**Interfaces:**
- Produces: 首页统计、快捷入口在 <=768px 下纵向排列。

- [ ] **Step 1: 添加 768px 与 480px 媒体查询**

在 `<style scoped>` 末尾新增：
```css
@media (max-width: 768px) {
  .home-page { padding: 16px; }
  .home-page .summary,
  .home-page .stats,
  .home-page .quick-actions {
    grid-template-columns: 1fr;
  }
  .home-page .page-title { font-size: 22px; margin-bottom: 16px; }
}
@media (max-width: 480px) {
  .home-page { padding: 12px; }
  .home-page .page-title { font-size: 20px; }
}
```

- [ ] **Step 2: 验证**

在 375px / 768px / 1200px 下访问首页。
Expected: 统计卡片在小屏下纵向堆叠，无横向滚动。

- [ ] **Step 3: Commit**

```bash
git add faheng-web/src/views/HomeView.vue
git commit -m "feat: 首页响应式卡片布局"
```

---

### Task 5: 起草页（DraftView）响应式

**Files:**
- Modify: `faheng-web/src/views/DraftView.vue`

**Interfaces:**
- Produces: 页面标题区换行、修订行纵向排列、上传区全宽、A4 区流式宽度。

- [ ] **Step 1: 修改页面标题操作区**

找到 `.page-head` / `.head-actions` 样式，追加：
```css
@media (max-width: 768px) {
  .page-head { flex-wrap: wrap; gap: 12px; padding: 16px; }
  .head-actions { flex-wrap: wrap; width: 100%; justify-content: flex-start; }
  .head-actions .el-button { flex: 1 1 auto; min-width: 96px; }
}
```

- [ ] **Step 2: 修订行移动端纵向排列**

找到 `.revise-row` 样式，追加：
```css
@media (max-width: 768px) {
  .revise-row { flex-direction: column; align-items: stretch; gap: 12px; }
  .revise-row .el-input,
  .revise-row .el-button { width: 100%; margin-left: 0 !important; }
}
```

- [ ] **Step 3: 上传区宽度**

在 `.upload-zone` / `.upload-panel` 相关样式处（如本文件有引用）追加：
```css
@media (max-width: 768px) {
  .upload-zone { max-width: 100%; }
}
```

- [ ] **Step 4: 验证**

在 375px / 768px / 1200px 下访问 `/draft`。
Expected:
- 标题区按钮换行；修订输入框与按钮纵向排列；上传区占满宽度；桌面端不变。

- [ ] **Step 5: Commit**

```bash
git add faheng-web/src/views/DraftView.vue
git commit -m "feat: 起草页标题区、修订行、上传区响应式"
```

---

### Task 6: A4 编辑器与合同预览区响应式

**Files:**
- Modify: `faheng-web/src/components/RichEditor.vue`
- Modify: `faheng-web/src/components/ContractPane.vue`

**Interfaces:**
- Produces: A4 容器在移动端改为流式宽度 + 等比缩放或减小 padding，工具栏自动换行。

- [ ] **Step 1: RichEditor 移动端样式**

在 `<style scoped>` 中找到 `.editor-paper` / `.paper` 相关样式，追加：
```css
@media (max-width: 768px) {
  .editor-paper { max-width: 100%; padding: 16px; min-height: 60vh; }
  .editor-toolbar { gap: 8px; }
  .editor-toolbar .el-button { padding: 6px 8px; }
}
@media (max-width: 480px) {
  .editor-paper { padding: 12px; }
}
```

- [ ] **Step 2: ContractPane 移动端样式**

找到 `.contract-content` / `.file` 样式，追加：
```css
@media (max-width: 768px) {
  .contract-pane { padding: 12px; }
  .contract-content { max-width: 100%; padding: 16px; }
  .file { max-width: 100%; }
}
```

- [ ] **Step 3: 验证**

在起草/审查页打开富文本编辑器与合同预览。
Expected: 375px 下 A4 区域不溢出，文字可读，工具栏换行但不遮挡内容。

- [ ] **Step 4: Commit**

```bash
git add faheng-web/src/components/RichEditor.vue faheng-web/src/components/ContractPane.vue
git commit -m "feat: A4 编辑器与合同预览区移动端流式宽度"
```

---

### Task 7: 审查页（ReviewView）移动端 Tab/抽屉重构

**Files:**
- Modify: `faheng-web/src/views/ReviewView.vue`

**Interfaces:**
- Produces: 在 <=768px 下，风险清单、合同正文、意见面板以 `el-tabs` 或分段抽屉切换；>768px 保持三栏。

- [ ] **Step 1: 新增移动端 Tab 状态与数据**

在 `<script setup>` 中新增：
```js
import { ref, computed, onMounted, onUnmounted } from 'vue'

const activeMobileTab = ref('risk')
const isMobileLayout = ref(false)

function checkLayout() {
  isMobileLayout.value = window.innerWidth <= 768
}
onMounted(() => { checkLayout(); window.addEventListener('resize', checkLayout) })
onUnmounted(() => { window.removeEventListener('resize', checkLayout) })
```

- [ ] **Step 2: 修改模板：桌面三栏与移动 Tab 二选一**

将现有三栏容器包裹为：
```vue
<template>
  <div class="review-page">
    <div class="page-head">...</div>

    <!-- 桌面三栏 -->
    <div v-if="!isMobileLayout" class="workspace desktop-workspace">
      <RiskListPane class="panel risk-panel" />
      <ContractPane class="panel contract-panel" />
      <OpinionPane class="panel opinion-panel" />
    </div>

    <!-- 移动 Tab -->
    <div v-else class="mobile-workspace">
      <el-tabs v-model="activeMobileTab" class="mobile-tabs" stretch>
        <el-tab-pane label="风险" name="risk"><RiskListPane /></el-tab-pane>
        <el-tab-pane label="合同" name="contract"><ContractPane /></el-tab-pane>
        <el-tab-pane label="意见" name="opinion"><OpinionPane /></el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>
```

- [ ] **Step 3: 添加 scoped CSS**

在 `<style scoped>` 末尾追加：
```css
.mobile-workspace { padding: 12px; }
.mobile-tabs { --el-tabs-header-height: 44px; }
@media (max-width: 768px) {
  .page-head { flex-wrap: wrap; gap: 12px; padding: 16px; }
}
```

- [ ] **Step 4: 验证**

在 375px / 768px / 1200px 下访问 `/review`。
Expected:
- 1200px：三栏布局，与之前一致。
- 768px 及以下：出现“风险/合同/意见” Tab，切换正常，每栏内容可滚动，无横向溢出。

- [ ] **Step 5: Commit**

```bash
git add faheng-web/src/views/ReviewView.vue
git commit -m "feat: 审查页移动端改为 Tab 切换布局"
```

---

### Task 8: 意见面板（OpinionPane）决策按钮响应式

**Files:**
- Modify: `faheng-web/src/components/OpinionPane.vue`

**Interfaces:**
- Produces: 决策按钮网格在窄屏下改为 1 列或 2 列，避免文字竖排。

- [ ] **Step 1: 修改按钮网格样式**

找到 `.opinion-actions` 或 `.decision-btns` 样式（具体类名以文件为准），追加：
```css
@media (max-width: 768px) {
  .opinion-actions { grid-template-columns: 1fr; gap: 10px; }
  .opinion-actions .el-button { white-space: normal; line-height: 1.4; padding: 10px 12px; }
}
```

- [ ] **Step 2: 验证**

在审查页打开意见面板，检查 375px 下三个决策按钮是否正常纵向堆叠、无文字竖排。

- [ ] **Step 3: Commit**

```bash
git add faheng-web/src/components/OpinionPane.vue
git commit -m "feat: 意见面板决策按钮移动端堆叠"
```

---

### Task 9: 履约页（ComplianceView）响应式

**Files:**
- Modify: `faheng-web/src/views/ComplianceView.vue`

**Interfaces:**
- Produces: 统计区、过滤区、卡片网格、表格在移动端正常堆叠与滚动。

- [ ] **Step 1: 标题与过滤区换行**

在 `<style scoped>` 末尾追加：
```css
@media (max-width: 768px) {
  .compliance-page { padding: 16px; }
  .page-head { flex-wrap: wrap; gap: 12px; }
  .filter-bar { flex-wrap: wrap; gap: 10px; }
  .filter-bar .el-input,
  .filter-bar .el-select { width: 100%; }
}
```

- [ ] **Step 2: 统计区与卡片网格**

追加：
```css
@media (max-width: 768px) {
  .summary, .stats { grid-template-columns: 1fr 1fr; }
  .cards { grid-template-columns: 1fr; }
}
@media (max-width: 480px) {
  .summary, .stats { grid-template-columns: 1fr; }
}
```

- [ ] **Step 3: 验证**

在 375px / 768px / 1200px 下访问 `/compliance`。
Expected: 小屏下统计 2 列/1 列，卡片单列，过滤区换行，无横向滚动。

- [ ] **Step 4: Commit**

```bash
git add faheng-web/src/views/ComplianceView.vue
git commit -m "feat: 履约页统计、过滤、卡片响应式"
```

---

### Task 10: 表格组件横向滚动

**Files:**
- Modify: `faheng-web/src/components/MilestoneTable.vue`
- Modify: `faheng-web/src/components/ReportPanel.vue`

**Interfaces:**
- Produces: 表格外层滚动容器，确保小屏下可横向滚动查看全部列。

- [ ] **Step 1: MilestoneTable 添加滚动容器**

在模板中为 `el-table` 添加外层 `div`：
```vue
<div class="table-scroll-wrap">
  <el-table ... />
</div>
```
并在样式中追加：
```css
.table-scroll-wrap { overflow-x: auto; width: 100%; }
.table-scroll-wrap .el-table { min-width: 600px; }
@media (max-width: 768px) {
  .table-scroll-wrap { -webkit-overflow-scrolling: touch; }
}
```

- [ ] **Step 2: ReportPanel 添加滚动容器**

同上：若 ReportPanel 内是 `el-table`，则包裹 `.table-scroll-wrap` 并设置 `min-width`（根据列数，如 520px）。

- [ ] **Step 3: 验证**

在 375px 下访问包含表格的页面。
Expected: 表格区域可左右滚动，列头与内容完整显示，页面整体无横向滚动。

- [ ] **Step 4: Commit**

```bash
git add faheng-web/src/components/MilestoneTable.vue faheng-web/src/components/ReportPanel.vue
git commit -m "feat: 表格组件支持移动端横向滚动"
```

---

### Task 11: 弹窗、上传区、加载条、通知面板响应式

**Files:**
- Modify: `faheng-web/src/components/ContractCards.vue`
- Modify: `faheng-web/src/components/UploadZone.vue`
- Modify: `faheng-web/src/components/UploadPanel.vue`
- Modify: `faheng-web/src/components/LoadingIndicator.vue`
- Modify: `faheng-web/src/components/NotificationBell.vue`
- Modify: `faheng-web/src/components/StatsStrip.vue`
- Modify: `faheng-web/src/components/RiskListPane.vue`

**Interfaces:**
- Consumes: 全局弹窗宽度覆盖（Task 1）。
- Produces: 各组件在 <=768px 与 <=480px 下的宽度/间距/字体调整。

- [ ] **Step 1: ContractCards 弹窗与卡片**

在 ContractCards 中移除硬编码 `width="460px"`，改为：
```vue
<el-dialog :width="dialogWidth" ...>
```
并在 `<script setup>` 中：
```js
import { computed } from 'vue'
const dialogWidth = computed(() => window.innerWidth <= 768 ? 'calc(100% - 32px)' : '460px')
```
卡片网格追加：
```css
@media (max-width: 768px) {
  .cards { grid-template-columns: 1fr; }
}
```

- [ ] **Step 2: UploadZone / UploadPanel**

在各自 scoped style 追加：
```css
@media (max-width: 768px) {
  .upload-zone, .upload-panel { max-width: 100%; padding: 16px; }
}
```

- [ ] **Step 3: LoadingIndicator**

将固定宽度 `width: 400px` 改为响应式：
```css
.loading-bar { width: min(400px, calc(100% - 32px)); }
```

- [ ] **Step 4: NotificationBell**

将 `width="340"` 改为：
```vue
<el-popover :width="popoverWidth" ...>
```
```js
const popoverWidth = computed(() => window.innerWidth <= 768 ? Math.min(340, window.innerWidth - 32) : 340)
```

- [ ] **Step 5: StatsStrip**

追加：
```css
@media (max-width: 768px) {
  .stats-strip { flex-wrap: wrap; gap: 12px; }
  .stat-item { flex: 1 1 45%; }
}
@media (max-width: 480px) {
  .stat-item { flex: 1 1 100%; }
}
```

- [ ] **Step 6: RiskListPane 过滤按钮**

追加：
```css
@media (max-width: 768px) {
  .filter-row { flex-wrap: wrap; gap: 8px; }
  .filter-btn { flex: 1 1 auto; white-space: normal; }
}
```

- [ ] **Step 7: 验证**

依次检查各组件在 375px 下：弹窗不贴边、上传区全宽、加载条不溢出、通知面板不贴边、统计条正常换行、风险过滤按钮可点。

- [ ] **Step 8: Commit**

```bash
git add faheng-web/src/components/ContractCards.vue faheng-web/src/components/UploadZone.vue faheng-web/src/components/UploadPanel.vue faheng-web/src/components/LoadingIndicator.vue faheng-web/src/components/NotificationBell.vue faheng-web/src/components/StatsStrip.vue faheng-web/src/components/RiskListPane.vue
git commit -m "feat: 弹窗、上传、加载、通知、统计、过滤组件响应式"
```

---

### Task 12: 端到端验证与修复

**Files:**
- 可能修改：前面各任务涉及的文件（按需修复）。

**Interfaces:**
- Consumes: 前面所有 Task 的实现。

- [ ] **Step 1: 在 DevTools 下遍历所有路由**

访问 `/login`、`/`、`/draft`、`/review`、`/compliance`，分别在 375px、390px、480px、768px、1024px、1440px 下检查：
- 无横向滚动条（除表格内部滚动外）。
- 弹窗、下拉菜单、抽屉不贴边、不截断。
- 所有按钮文字正常横向或换行，不出现纵向单个字。
- 可点击区域不小于 44×44px。

- [ ] **Step 2: 记录并修复残余问题**

对发现的问题：在对应文件中添加/修改媒体查询样式；每个修复单独小提交。

- [ ] **Step 3: 运行构建**

Run: `cd /home/otto/ezContract/faheng-web && npm run build`
Expected: 构建成功，无新增 ESLint / TypeScript 错误。

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "fix: 移动端适配端到端验证与细节修复"
```

---

## Self-Review

**1. Spec coverage:**
- 字体纵向排列问题 → Task 8（意见按钮）、Task 11（StatsStrip/RiskListPane）。
- 窗口显示不全 → Task 1（弹窗）、Task 6（A4 编辑器）、Task 7（审查 Tab）、Task 11（各弹窗/通知）。
- 顶部导航挤压 → Task 2。
- 表格截断 → Task 10。
- 审查三栏 → Task 7。
- 上传区/加载条 → Task 11。
- 首页/履约/起草 → Task 4、5、9。

**2. Step scan：** 每步只决定一个合理动作；CSS 样式值为具体值；验证命令明确。

**3. Type consistency：** 使用 `window.innerWidth`、`isMobileLayout` 等命名在 Task 2、7 中一致；`el-dialog :width` 统一使用计算属性。

**4. Review Focus：** 五项重点均已在 Task 12 验证步骤中检查。

**5. Proportion：** 计划长度与问题范围相称，未提前写出具体 CSS 选择器细节，保留了实现者根据实际类名调整的余地。
