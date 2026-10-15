import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useItineraryStore } from '../stores/itinerary'

/**
 * 录音状态机（模块级单例）：悬浮语音按钮与当日弹框语音按钮是同一台机器
 * 的两个控制面板，跨页面由全局浮标承接，路由切换不销毁。
 *
 * 职责：能力探测（HTTPS getUserMedia / HTTP 系统录音器兜底）、
 * idle → starting → recording → processing 状态机、冷却防抖、
 * 转写+解析（store.parseVoiceAudio）。
 * 业务语义（来源、默认日期、解析结果去向）由 start(opts) 调用方注入，
 * 并在 start 时快照——路由往返后 store.selectedDate/selectedArtistId
 * 可能被 initMonth()/重新加载重置，上传必须用发起时的值。
 *
 * 防并发（决策 1）：start() 在非 idle 相位一律拒绝（ElMessage 提示），
 * 物理上同一时刻只有一条录音。toggle() 的停止分支不受此限——
 * 录音中点同一按钮是正当的停止操作。
 */

// ── 模块级单例状态（唯一一份）──
const phase = ref('idle')
const startedAt = ref(0)
// 来源标记：仅用于弹框关闭时判断是否停止（决策 3 只作用于 dialog 来源）
const source = ref(null) // 'fab' | 'dialog' | null
let _snap = null // { date, artistId, onResult } —— start 时快照
let lockUntil = 0
const COOLDOWN_MS = 1000

// 录音：getUserMedia + MediaRecorder
let mediaStream = null
let mediaRecorder = null
let audioChunks = []
let stopTimer = null

// 录音能力探测：getUserMedia 仅在安全上下文（HTTPS / localhost）可用。
// 公网 IP 用 HTTP 直连时 navigator.mediaDevices 为 undefined → 走系统录音器上传兜底
let _probed = false
let _useFallback = false

function _probeOnce() {
  if (_probed) return
  _probed = true
  const nativeSupported =
    typeof window !== 'undefined' &&
    window.isSecureContext &&
    !!(navigator.mediaDevices?.getUserMedia) &&
    typeof MediaRecorder !== 'undefined'
  _useFallback = !nativeSupported
}

function _getStarted() {
  return Date.now()
}

/** 立即停止录音并释放麦克风（不等待 onstop 回调清理） */
function stop() {
  clearTimeout(stopTimer)
  stopTimer = null
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    try {
      mediaRecorder.stop() // 触发 onstop → 进入转写流程
    } catch {
      // ignore
    }
  }
  mediaStream?.getTracks().forEach((t) => t.stop()) // 麦克风指示灯立即熄灭
}

function cleanupRecording() {
  clearTimeout(stopTimer)
  stopTimer = null
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    // 丢弃式停止：先摘掉 onstop，避免硬复位（登出/鉴权失效）路径把
    // 用户已放弃的录音继续上传转写，并异步回践 phase 造成状态竞态。
    // 正常点按结束走 stop() → onstop，不受影响。
    mediaRecorder.onstop = null
    try {
      mediaRecorder.stop()
    } catch {
      // ignore
    }
  }
  mediaRecorder = null
  mediaStream?.getTracks().forEach((t) => t.stop())
  mediaStream = null
  audioChunks = []
}

function pickMimeType() {
  // 常见浏览器录音格式优先级；后端统一转码
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
    'audio/mpeg',
  ]
  for (const type of candidates) {
    if (MediaRecorder.isTypeSupported?.(type)) return type
  }
  return ''
}

/** 转写 + 解析共用出口：上传用 start 时的快照（日期/人员），成功后回调快照 onResult */
async function processBlob(blob, filename) {
  phase.value = 'processing'
  const snap = _snap
  try {
    await store().parseVoiceAudio(blob, filename, snap?.date, snap?.artistId)
    snap?.onResult?.()
    _snap = null
  } catch {
    // error handled in store
    _snap = null
  } finally {
    phase.value = 'idle'
    lockUntil = Date.now() + COOLDOWN_MS
  }
}

/** 兜底通道：动态建 <input type=file capture>，选完文件直接上传转写（走快照） */
function openFilePicker() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'audio/*'
  input.capture = ''
  input.style.display = 'none'
  input.onchange = async (e) => {
    const file = e.target.files?.[0]
    document.body.removeChild(input)
    if (!file) return
    // 文件大小与后端 _MAX_AUDIO_BYTES 对齐
    if (file.size > 20 * 1024 * 1024) {
      ElMessage.warning('录音文件过大（超过 20MB），请缩短录音时长')
      _snap = null
      phase.value = 'idle'
      return
    }
    await processBlob(file, file.name)
  }
  document.body.appendChild(input)
  input.click()
}

async function start(opts) {
  const { source: src, getDefaultDate, onResult } = opts || {}
  // 防抖：启动中 / 录音中 / 识别上传中 / 冷却期内，一律拒绝（决策 1：
  // 提示进行中而非静默忽略——两入口并发是真实场景）
  if (phase.value !== 'idle' || Date.now() < lockUntil) {
    if (phase.value !== 'idle') ElMessage.warning('语音录入进行中')
    return
  }

  _probeOnce()
  // 快照（裁决 3）：日期/人员在 start 时定格，路由往返后仍用发起时的值
  _snap = {
    date: getDefaultDate?.(),
    artistId: store().selectedArtistId,
    onResult,
  }
  source.value = src || null
  startedAt.value = _getStarted()

  // 兜底通道：调起系统录音器（录完自动回来走 parse-voice-audio）。
  // 也置 starting（裁决 6）：防重入与快照对兜底路径同样生效
  if (_useFallback) {
    phase.value = 'starting'
    openFilePicker()
    return
  }

  phase.value = 'starting'
  let stream
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  } catch (e) {
    phase.value = 'idle'
    _snap = null
    startedAt.value = 0
    if (e?.name === 'NotAllowedError') {
      ElMessage.error('麦克风权限未开启，请在浏览器地址栏允许麦克风后重试')
    } else {
      ElMessage.error('无法访问麦克风：' + (e?.message || e))
    }
    return
  }

  mediaStream = stream
  audioChunks = []
  let mimeType = ''
  try {
    mimeType = pickMimeType()
    mediaRecorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream)
  } catch {
    // 极少数环境 MediaRecorder 构造失败：释放权限并提示
    cleanupRecording()
    phase.value = 'idle'
    _snap = null
    startedAt.value = 0
    ElMessage.error('当前浏览器录音初始化失败，请换用 Chrome/Edge 或系统录音上传')
    return
  }

  mediaRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size > 0) audioChunks.push(e.data)
  }

  mediaRecorder.onstop = async () => {
    const blob = new Blob(audioChunks, {
      type: mediaRecorder?.mimeType || 'audio/webm',
    })
    cleanupRecording()

    if (!blob.size) {
      phase.value = 'idle'
      _snap = null
      startedAt.value = 0
      // 录音数据为空是本地问题（未授权/极短）；真正录到内容但 ASR
      // 识别为空的提示由后端 422 返回，避免这里弹两次
      ElMessage.warning('未能录到声音，请检查麦克风权限后重试')
      return
    }
    await processBlob(blob)
  }

  phase.value = 'recording'
  const s = store()
  s.voiceText = ''
  s.voiceParsedEvents = []
  try {
    // timeslice 500ms：ondataavailable 持续产出分片，避免个别浏览器
    // 只在 stop 时一次性给数据导致的"停止无响应"问题
    mediaRecorder.start(500)
  } catch {
    mediaRecorder.start()
  }
  // 不设自动停止：语音内容长短不一，由用户点按结束；
  // 转写接口上限 20MB，opus 低码率录音远达不到，无需代管
}

/** 点击行为统一入口：录音中 = 停止并提交；其他状态（含另一入口发起的
 * 录音）走 start 分支 → 被防并发拒绝。同一按钮的停止不受决策 1 限制。 */
function toggle(opts) {
  if (phase.value === 'recording') {
    stop()
    return
  }
  start(opts)
}

/** 硬复位（登出 / 鉴权失效进全屏路由）：停止并丢弃，不提交——
 * token 已失效，提交必 401（裁决 4/5） */
function resetVoiceRecorder() {
  cleanupRecording()
  lockUntil = 0
  _snap = null
  source.value = null
  startedAt.value = 0
  phase.value = 'idle'
}

// store 在模块顶层引用会在 Pinia 安装前求值报错，惰性获取
function store() {
  return useItineraryStore()
}

/** 单例视图：任意组件调用返回同一份状态与操作（无参） */
export function useVoiceRecorder() {
  return {
    phase,
    startedAt,
    source,
    start,
    stop,
    toggle,
    isBusy: () => phase.value !== 'idle',
  }
}

export { resetVoiceRecorder }
