# 语音录入会话化改造 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 录音状态机单例化，两个入口（悬浮 FAB / 当日弹框按钮）变为同一状态机的控制面板，跨页面由全局浮标承接，路由切换不再销毁录音。

**Architecture:** `useVoiceRecorder.js` 从「每次调用创建实例」改为模块级单例：`phase` / `startedAt` / 来源标记 / 快照（default_date、artist、onResult）全部模块级共享，`start()` 拒绝非 idle 相位重入。新增 `VoiceGlobalIndicator.vue` 挂在 App.vue，订阅单例状态，仅当 `phase ≠ idle && route.path !== '/itinerary' && !isFullscreen` 时渲染。登出/进全屏路由时单例硬复位（丢弃）。

**Tech Stack:** Vue 3 `<script setup>` + Element Plus + Pinia；无前端测试设施，验证 = `npx vite build` 0 error + 代码走查清单（录音行为需浏览器）。

**Spec:** [docs/superpowers/specs/2026-10-15-voice-session-design.md](../specs/2026-10-15-voice-session-design.md)（含 7 项 builder check 补充裁决，编号裁决 1-7，下文引用为「裁决 N」）

## Global Constraints

- 「人员」文案规范；`artist_id` 等接口字段名**不动**（spec 约束）
- 现有防抖语义必须保留：idle → starting → recording → processing + 1s 冷却（spec 约束）
- 决策 1：非 idle 相位（starting/recording/processing）点任何入口 → `ElMessage` 提示拒绝，不停止当前录音（spec 决策 1 + 裁决 2 末句）
- 决策 2：路由切换**不**销毁录音；组件卸载路径不调 stop（spec 裁决 1）
- 决策 3：el-dialog `@close` 且来源为 dialog 且 `phase === 'recording'` → stop() 提交；`processing` 不动（spec 决策 3 + 裁决 2）
- 快照时机：`start()` 时快照 `defaultDate`（调 `getDefaultDate()`）与 `defaultArtistId`（读 `store.selectedArtistId`），上传时用快照（spec 裁决 3）
- 登出/进全屏路由：单例硬复位（停止并丢弃，不提交）（spec 裁决 4、5）
- 兜底文件路径：fallback 分支也置 `starting`，选完文件转 `processing`；快照同样生效（spec 裁决 6）
- 计时器：`Date.now()` 墙钟，每 tick 从 startedAt 重算，mm:ss（spec 裁决 7）
- 悬浮按钮现有样式块**逐字节不动**（上一轮修复已对齐 base，不再漂移）

## Review Focus

1. **FAB 录音中用户打开弹框点弹框语音按钮** → 拒绝提示「语音录入进行中」，FAB 录音不受影响（决策 1；Task 1 走查项 + 手测场景）
2. **dialog 来源录音中用户点 FAB** → 同样拒绝；FAB 也不得因此开始第二条录音（决策 1 对称；Task 1 走查项）
3. **dialog 来源录音中路由切走再回来，点结束** → 提交的 default_date 仍是当初点击那天，不是今天（裁决 3——`initMonth()` 会重置 selectedDate；Task 1 快照逻辑 + Task 4 手测场景）
4. **processing 中路由切走** → 浮标显示「语音识别中…」，完成后 toast「语音已解析…」；回到行程页确认框可见（spec 浮标两态；Task 3）
5. **录音中登出/被踢到 /login** → 麦克风释放、无残留状态、无 401 请求（裁决 5；Task 3 走查项）

---

### Task 1: 单例状态机改造（useVoiceRecorder.js）

**Files:**
- Modify: `faheng-web/src/composables/useVoiceRecorder.js`（结构性重写，文件唯一）

**Interfaces:**
- Consumes: 现有 store.parseVoiceAudio(blob, filename, defaultDate)
- Produces（Task 2/3/4 依赖的导出形状，签名固定）:
  - `useVoiceRecorder()` —— **无参数**，返回单例视图：`{ phase, startedAt, source, start(opts), stop(), toggle(opts), isBusy() }`
  - `start(opts: { source: 'fab' | 'dialog', getDefaultDate?: () => string | undefined, onResult?: () => void })` —— 非 idle 相位时 `ElMessage.warning('语音录入进行中')` 并 return（不 throw）；快照 `_snap = { date: opts.getDefaultDate?.(), artistId: store.selectedArtistId, onResult: opts.onResult, source: opts.source }`；fallback 分支也置 `phase.value = 'starting'`
  - `stop()` —— 现有 forceStopRecording 逻辑（stop() 触发 onstop → 提交链路）
  - `toggle(opts)` —— `phase === 'recording'` 时 stop()，否则 `start(opts)`（注意：toggle 的停止分支**不**拒绝——录音中点同一按钮就是停止，决策 1 只挡「开始」）
  - `isBusy()` —— `phase.value !== 'idle'`（模板禁用态用）
  - 模块级内部 `_hardReset()` —— 摘 onstop、停 tracks、清快照、phase 归 idle；不导出，通过新增导出 `resetVoiceRecorder()` 暴露给 Task 3 的登出钩子（裁决 4/5）
  - 上传调用改为：`store.parseVoiceAudio(blob, filename, _snap?.date)`，且 `store.selectedArtistId` 传参处改用快照——通过给 `parseVoiceAudio` 增加第四参 `defaultArtistId` 实现（见 Step 2）
  - `onstop` 空数据/上传失败路径不变；成功路径调 `_snap?.onResult?.()` 后清快照
  - 计时器：`start()` 成功进入 recording/starting 时 `_startedAt = Date.now()`（导出 `startedAt` ref）；不在此文件起 interval（浮标自己算，Task 3）

**关于 `toggle` 与决策 1 的辨析**（写死在计划里防止实现者跑偏）：拒绝重入挡的是 `start()`；`toggle` 在 recording 相位执行的是 stop 语义，这是用户点「正在听·点击结束」的正当操作。但**跨入口**的 toggle（FAB 开始录音、点弹框按钮）必须落到 `start` 分支被拒——所以 `toggle(opts)` 实现为 `phase === 'recording' ? stop() : start(opts)`，弹框/FAB 的点击处理函数统一走 toggle，拒绝逻辑自然生效。

- [ ] **Step 1: 重写 composable 为单例**

按 Interfaces 块实现。要点：模块级单例状态（phase、startedAt、source、快照、mediaStream/mediaRecorder/audioChunks/lockUntil）+ `useVoiceRecorder()` 函数只返回视图（ref 直接返回引用，函数闭包引用单例）；`onMounted` 能力探测移到模块级**惰性执行一次**（`_probeOnce`，无组件生命周期可挂）；删除 `dispose` 对外导出（`resetVoiceRecorder` 取代）；`busy` getter 删除（无消费方，上轮 deferred minor 一并清理）。

- [ ] **Step 2: store.parseVoiceAudio 增加快照人员参数**

`faheng-web/src/stores/itinerary.js`：`parseVoiceAudio(blob, filename, defaultDate, defaultArtistId)` —— `form.append('default_artist_id', defaultArtistId ?? this.selectedArtistId)`（快照优先，未传回退现状）。其余不动。悬浮/弹框调用方在 Task 2/4 改造后均由单例传快照。

- [ ] **Step 3: 构建验证**

Run: `cd faheng-web && npx vite build`
Expected: 会报错——`VoiceInputButton.vue` / `DayDetailDrawer.vue` 仍按旧签名调用（`useVoiceRecorder({ onResult })`、`rec.dispose()`）。**这是预期的中间态**，Task 2 立即修复；本步只确认错误仅限这两个文件、无语法级新错误（composable 本身可编译）。

- [ ] **Step 4: 走查清单（代码级验证，替代测试）**

逐项核对（读代码确认，非猜测）：
- [ ] 模块级只有一份 `mediaStream` / `lockUntil` / `_snap` —— grep 无第二处声明
- [ ] `start()` 第一行非 idle 即 `ElMessage.warning('语音录入进行中')` + return（决策 1，覆盖 starting/recording/processing）
- [ ] fallback 分支置 `starting`（裁决 6）；`openFilePicker` 的 onchange 走快照的 date/artist
- [ ] `onstop` 提交用 `_snap.date` / `_snap.artistId`（裁决 3）；提交后 `_snap = null`
- [ ] `resetVoiceRecorder()` 摘 onstop 再 stop、停 tracks、清快照、`phase = 'idle'`（裁决 4/5，沿用上轮「不上传已放弃录音」结论）
- [ ] `cleanupRecording` 内部逻辑未被破坏（丢弃式停止语义保留）

- [ ] **Step 5: Commit**

```bash
git add faheng-web/src/composables/useVoiceRecorder.js faheng-web/src/stores/itinerary.js
git commit -m "refactor(itinerary): 录音状态机单例化——防并发/快照/硬复位（语音会话化 1/3）"
```

注：此时 build 红（两调用方未适配），提交注明「Task 2 修复调用方」。若仓库惯例要求每提交可构建，改为把 Task 1+2 合并提交，但**任务边界与走查仍按本计划分开执行**。

---

### Task 2: 两个入口改造为控制面板

**Files:**
- Modify: `faheng-web/src/components/itinerary/VoiceInputButton.vue`（script + template；style 块逐字节不动）
- Modify: `faheng-web/src/components/itinerary/DayDetailDrawer.vue`
- Modify: `faheng-web/src/components/itinerary/DayDetailContent.vue`（语音按钮三态渲染）

**Interfaces:**
- Consumes: Task 1 的 `useVoiceRecorder()` / `start(opts)` / `toggle(opts)` / `isBusy()` / `phase` / `startedAt`
- Produces: 无（叶子组件）；行为契约——
  - FAB：`rec.toggle({ source: 'fab', onResult: () => { store.voiceDialogVisible = true } })`（FAB 无 defaultDate——悬浮路径语音里说日期）；recording 中红色脉冲 + 「正在听（点击结束）」、processing 转圈「识别中…」（现状保留）；**删除 `onBeforeUnmount(rec.dispose)`**（决策 2）
  - 弹框按钮（DayDetailContent 内，emit('voice') 上抛不变）：三态 = 默认 `语音录入` / recording `正在听·点击结束`（type 变 `danger`、`rec.isBusy() && source === 'dialog'` 时）/ processing `识别中…`（`:loading`）；**非本来源 busy**（`rec.isBusy() && 单例 source !== 'dialog'`）时 `disabled` + tooltip「语音录入进行中」（裁决 2）
  - DayDetailDrawer：`rec.toggle({ source: 'dialog', getDefaultDate: () => store.selectedDate, onResult: () => { store.voiceDialogVisible = true } })`；el-dialog `@close` 改为：`if (rec.source === 'dialog' && rec.phase === 'recording') rec.stop()`（决策 3 + 裁决 2——仅 dialog 来源、仅用户显式关闭）；删除 `onDialogClose` 里的无条件 dispose；**不挂 onBeforeUnmount 清理**（决策 2/裁决 1）

- [ ] **Step 1: 改造 VoiceInputButton**

script 按 Interfaces 重写（人员校验保留在 onClick：`!store.selectedArtistId` → warning + return）；模板绑定从 `rec.xxx.value` 改为解构或保持（单例返回的 ref 用法不变）；style 块不动。

- [ ] **Step 2: 改造 DayDetailContent 语音按钮三态 + DayDetailDrawer**

按 Interfaces 实现。DayDetailContent 需要感知单例状态：直接在组件内 `useVoiceRecorder()` 取 `phase`/`startedAt`（单例无参调用随处可用），emit('voice') 保持上抛。DayDetailDrawer 的 `@close` 处理见上。注：`rec.source` 需从 `useVoiceRecorder()` 返回值暴露（Task 1 已定）。

- [ ] **Step 3: 构建验证**

Run: `cd faheng-web && npx vite build`
Expected: 0 error

- [ ] **Step 4: 走查清单**

- [ ] FAB：`grep -n dispose VoiceInputButton.vue` 无结果（决策 2）；style 块与 base 逐字节一致（`git diff 7546720 -- ...VoiceInputButton.vue` 的 style 段为空）
- [ ] 弹框按钮三态渲染条件正确（同源 recording 红/可点结束；异源 disabled+tooltip）
- [ ] `@close` 只在 `source === 'dialog' && phase === 'recording'` 时 stop；processing 时不动作
- [ ] DayDetailDrawer 无 onBeforeUnmount 清理
- [ ] FAB 点击处理在 busy 时不会二次触发 getUserMedia（toggle→start→拒绝路径）

- [ ] **Step 5: Commit**

```bash
git add faheng-web/src/components/itinerary/VoiceInputButton.vue faheng-web/src/components/itinerary/DayDetailDrawer.vue faheng-web/src/components/itinerary/DayDetailContent.vue
git commit -m "feat(itinerary): FAB/弹框语音按钮改为单例控制面板，弹框按钮补三态（语音会话化 2/3）"
```

---

### Task 3: 全局浮标 VoiceGlobalIndicator + 登出硬复位

**Files:**
- Create: `faheng-web/src/components/VoiceGlobalIndicator.vue`
- Modify: `faheng-web/src/App.vue`（挂载浮标 + 登出硬复位）

**Interfaces:**
- Consumes: Task 1 的 `useVoiceRecorder()`（`phase` / `startedAt` / `stop()` / `source`）与 `resetVoiceRecorder()`
- Produces: 无（叶子）；行为契约——
  - 渲染条件：`phase !== 'idle' && route.path !== '/itinerary' && !isFullscreen && auth.isLoggedIn`（spec 浮标形态；+isLoggedIn：登出瞬间守卫切 /login 前浮标不该闪现）
  - 两态渲染：`phase === 'recording' || 'starting'` → `● 正在录音 mm:ss  ✕ 结束`（红点 CSS 呼吸动画；`✕ 结束` 按钮点击 = `rec.stop()`；starting 时结束按钮 disabled——裁决 6）；`phase === 'processing'` → `◌ 语音识别中…`（el-icon Loading 转圈，无操作）
  - 计时器：组件内 `setInterval` 1s，`elapsed = Date.now() - startedAt` 重算（不累加），`mm:ss` 格式（裁决 7）；onUnmounted 清 interval
  - 解析完成 toast：watch `phase` 从非 idle 变 idle 且**当前路由非 /itinerary** 且 `voiceParsedEvents.length > 0` → `ElMessage.success('语音已解析，回到「人员行程」确认')`；在 /itinerary 时不开 toast（确认框自己会开，onResult 已处理）
  - 样式：`position: fixed; right: 28px; bottom: 28px; z-index: 100`（移动端 `right: 16px; bottom: 16px`，对齐 FAB 位置）；el-card 风格白色胶囊、圆角、阴影；红点 `#e74c3c` 呼吸（animation opacity 循环）
- App.vue 登出钩子：`onLogout()`（现有函数）内加 `resetVoiceRecorder()`；另外 router 守卫进 `to.meta.fullscreen` 路由时同样硬复位——放 App.vue 的 `watch(() => route.fullPath)`（现有 watch 内，isFullscreen 分支）调用 `resetVoiceRecorder()`（裁决 5：登录页无浮标，必须在那里掐断；watch 已有 isFullscreen 分支，插一行即可）

- [ ] **Step 1: 创建 VoiceGlobalIndicator.vue**

按 Interfaces 实现。`useRoute()` 判路由；计时器 ref `elapsedText`。

- [ ] **Step 2: App.vue 挂载与硬复位接线**

template 在 `</main>` 后加 `<VoiceGlobalIndicator />`（组件内部自判渲染条件，App 不加 v-if）；`onLogout` 与 route watch 的 isFullscreen 分支加 `resetVoiceRecorder()`。

- [ ] **Step 3: 构建验证**

Run: `cd faheng-web && npx vite build`
Expected: 0 error

- [ ] **Step 4: 走查清单**

- [ ] 浮标渲染四条件齐全（phase/route/fullscreen/isLoggedIn）
- [ ] processing 态无操作面（只读展示）
- [ ] toast 只在非行程页弹；行程页内解析完成无 toast（确认框路径）
- [ ] interval 在 onUnmounted 清理；浮标只在可见时跑 interval（`v-if` 内层或 watch phase 控启停，二选一，实现者定）
- [ ] 登出 + 进 /login 两条路径都触发 `resetVoiceRecorder()`；reset 不产生上传请求
- [ ] 「语音已解析」toast 的触发条件里 `voiceParsedEvents.length > 0` 有值（失败/空结果不弹误导性 toast）

- [ ] **Step 5: Commit**

```bash
git add faheng-web/src/components/VoiceGlobalIndicator.vue faheng-web/src/App.vue
git commit -m "feat(itinerary): 跨页面录音浮标——计时/结束/识别态展示，登出硬复位（语音会话化 3/3）"
```

---

### Task 4: 手测清单（交付验收，无代码）

**Files:** 无（浏览器操作，用户或实现者在 dev server 上执行）

- [ ] FAB 录音 → 打开当日弹框点语音按钮 → 弹「语音录入进行中」toast，FAB 录音继续（红脉冲不停）
- [ ] 弹框录音 → 点 FAB → 同样拒绝；弹框按钮保持「正在听·点击结束」
- [ ] 弹框录音中点弹框内按钮（停止）→ 提交 → 确认框日期 = 点击那天
- [ ] 弹框录音中关闭弹框 → 自动停止提交 → 确认框弹出，日期仍是那天
- [ ] FAB 录音中关闭当日弹框 → FAB 录音**不**受影响（裁决 2：来源不是 dialog）
- [ ] 录音中切到「合同审查」页 → 浮标出现（红点+计时+结束）；点结束 → 提交 → toast「语音已解析…」；切回行程页 → 确认框可见，日期 = 发起时点击那天（裁决 3 手测）
- [ ] processing 中切页 → 浮标「语音识别中…」→ 完成后 toast
- [ ] 录音中登出 → 无 401 请求、麦克风指示灯灭、登录页无浮标
- [ ] HTTP 环境（公网 IP 直连）走系统录音器兜底：录音中切页无浮标中断，选完文件回来自动上传（裁决 6 手测）
- [ ] 悬浮按钮样式与改造前一致（对照 Task 2 Step 4 的 diff 检查已做过，目视再确认）

完成后在最终交付消息里逐项报告结果；未测项如实标注。
